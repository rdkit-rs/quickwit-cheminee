# frozen_string_literal: true
# Real local journals and process exits, fake server. No HTTP/indexing/HA claims.
require 'minitest/autorun'
require 'tmpdir'
require 'ostruct'
require 'timeout'
require_relative 'catalog_generation'

class JournalPeer
  attr_accessor :fault
  def initialize(path)
    @path = path
    persist('indices' => {}, 'calls' => 0)
  end
  def data
    JSON.parse(File.read(@path))
  end
  def persist(value)
    File.open(@path, 'w') { |f| f.write(JSON.generate(value)); f.flush; f.fsync }
  end
  def rows
    data.fetch('indices').transform_values { |records| records.map { |r| r.transform_keys(&:to_sym) } }
  end
  def calls
    data.fetch('calls')
  end
  def create_index(mapping, **)
    value = data
    value['indices'][mapping.fetch(:index_id)] = []
    persist(value)
    raise IOError, 'lost create acknowledgement' if fault == :lost_create_ack
  end
  def ingest(index, body, **)
    value = data
    value['calls'] += 1
    value['indices'].fetch(index).concat(body.lines.map { |line| JSON.parse(line) })
    persist(value) # Shared child/parent oracle, not a model of server durability.
    exit!(84) if fault == :exit_after_accept
    raise IOError, 'lost acknowledgement' if fault == :lost_ack
    OpenStruct.new(num_ingested_docs: fault == :missing_count ? nil : body.lines.length, num_rejected_docs: 0)
  end
  def search_composable_unchecked_with_http_info(index, body, **)
    rows = self.rows.fetch(index).sort_by { |r| r.fetch(:record_id) }
    hits = rows.drop(body.fetch(:from)).first(body.fetch(:size)).map do |r|
      {_index: index, _source: r, sort: [1.0, r.fetch(:record_id)]}
    end
    [{timed_out: false, _shards: {total: 1, successful: 1, failed: 0, skipped: 0},
      hits: {total: {value: rows.length, relation: 'eq'}, hits: hits}}, 200, {}]
  end
end

class ExitingJournal < CatalogGeneration
  attr_accessor :exit_at
  private
  def save(name, value)
    exit!(81) if exit_at == :before_pointer && name == 'active.json'
    super
    exit!(82) if exit_at == :after_pointer && name == 'active.json'
    exit!(85) if exit_at == :after_ack && value.fetch('batches', {}).values.any? { |b| b['status'] == 'acknowledged' }
    exit!(83) if exit_at == :before_dispatch && value.fetch('batches', {}).values.any? { |b| b['status'] == 'in_flight' }
  end
end

class FailingAcknowledgementJournal < CatalogGeneration
  private
  def save(name, value)
    if !@failed && value.fetch('batches', {}).values.any? { |b| b['status'] == 'acknowledged' }
      @failed = true
      raise IOError, 'injected acknowledgement persistence failure'
    end
    super
  end
end

class CatalogRecoveryTest < Minitest::Test
  def setup
    @directory = Dir.mktmpdir('catalog-recovery-')
    @api = JournalPeer.new(File.join(@directory, 'peer.json'))
    @store = reopen
  end
  def teardown
    FileUtils.remove_entry(@directory)
  end
  def reopen(klass = CatalogGeneration)
    klass.new(api: @api, directory: @directory, expected_suppliers: ['Acme'])
  end
  def snapshot(sequence, complete: true)
    {suppliers: ['Acme'], snapshots: [{supplier: 'Acme', sequence: sequence,
      complete: complete, observed_at: '2026-10-16T12:00:00Z',
      offers: [{offer_id: 'one', record_id: 1, smiles: 'C[C@H](O)Cl.Cl'}]}]}
  end
  def ready(sequence)
    generation = @store.stage(snapshot(sequence))
    @store.ingest(generation, batch_id: 'one', record_ids: [1])
    generation
  end
  def interrupted(generation, point, code)
    pid = fork do
      journal = reopen(ExitingJournal)
      journal.exit_at = point
      [:before_dispatch, :after_ack].include?(point) ? journal.ingest(generation, batch_id: 'one', record_ids: [1]) : journal.promote(generation)
      exit!(99)
    end
    _, status = Timeout.timeout(5) { Process.wait2(pid) }
    assert_equal code, status.exitstatus
  ensure
    begin
      if pid && Process.waitpid(pid, Process::WNOHANG).nil?
        Process.kill('KILL', pid); Process.waitpid(pid)
      end
    rescue Errno::ECHILD, Errno::ESRCH
    end
  end
  def state(generation)
    JSON.parse(File.read(File.join(@directory, "#{generation}.json")))
  end
  def test_interrupted_before_pointer_can_finish_without_reingest
    generation = ready(1)
    initial = @store.pointer
    interrupted(generation, :before_pointer, 81)
    assert_equal 'sealed', state(generation)['status']
    assert_equal initial, reopen.pointer
    calls = @api.calls
    assert_equal generation, reopen.promote(generation)
    assert_equal 1, reopen.pointer['revision']
    assert_equal calls, @api.calls
  end
  def test_pointer_is_authoritative_after_interrupted_promotion
    generation = ready(1)
    interrupted(generation, :after_pointer, 82)
    published = reopen.pointer
    assert_equal generation, published['active']
    assert_equal 'sealed', state(generation)['status']
    calls = @api.calls
    2.times { assert_equal generation, reopen.promote(generation) }
    assert_equal published, reopen.pointer
    assert_equal calls, @api.calls
    assert_equal 'promoted', state(generation)['status']
  end
  def test_sealed_stale_generation_cannot_replace_new_winner
    stale = ready(1)
    winner = ready(2)
    interrupted(stale, :before_pointer, 81)
    @store.promote(winner)
    published = @store.pointer
    assert_raises(CatalogGeneration::Unsafe) { reopen.promote(stale) }
    assert_equal published, reopen.pointer
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(stale, batch_id: 'one', record_ids: [1]) }
  end
  def test_delayed_retry_after_newer_promotion_does_not_resurrect_old_pointer
    old = ready(1)
    interrupted(old, :after_pointer, 82)
    newer = ready(2)
    @store.promote(newer)
    published = @store.pointer
    assert_raises(CatalogGeneration::Unsafe) { reopen.promote(old) }
    assert_equal published, reopen.pointer
  end
  def test_ambiguous_ack_is_never_blindly_replayed
    generation = @store.stage(snapshot(1))
    @api.fault = :lost_ack
    assert_raises(IOError) { @store.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal 1, @api.rows.fetch(generation).length # Peer accepted the write.
    @api.fault = nil
    calls = @api.calls
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_raises(CatalogGeneration::Unsafe) { reopen.promote(generation) }
    assert_equal calls, @api.calls
    assert_nil reopen.pointer['active']
  end
  def test_exit_after_intent_before_dispatch_quarantines_on_recovery
    generation = @store.stage(snapshot(1))
    interrupted(generation, :before_dispatch, 83)
    assert_empty @api.rows.fetch(generation)
    assert_equal 'in_flight', state(generation)['batches']['one']['status']
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal 'quarantined', state(generation)['status']
    assert_equal 0, @api.calls
  end
  def test_partial_and_out_of_order_refresh_leave_active_unchanged
    first = ready(1); @store.promote(first)
    second = ready(2); @store.promote(second)
    current = @store.pointer
    @store.rollback(expected_revision: current['revision'])
    rolled_back = @store.pointer
    assert_equal current['high_water'], rolled_back['high_water']
    assert_raises(CatalogGeneration::Unsafe) { reopen.stage(snapshot(3, complete: false)) }
    assert_raises(CatalogGeneration::Unsafe) { reopen.stage(snapshot(2)) }
    assert_raises(CatalogGeneration::Unsafe) { reopen.rollback(expected_revision: current['revision']) }
    assert_equal rolled_back, reopen.pointer
  end
  def test_acknowledged_duplicate_uses_journal_without_http
    generation = ready(1)
    calls = @api.calls
    assert_equal({'accepted' => 1, 'rejected' => 0}, reopen.ingest(generation, batch_id: 'one', record_ids: [1]))
    assert_equal calls, @api.calls
  end
  def test_acknowledgement_journal_failure_quarantines_without_replay
    generation = @store.stage(snapshot(1))
    journal = reopen(FailingAcknowledgementJournal)
    assert_raises(IOError) { journal.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal 1, @api.rows.fetch(generation).length
    assert_equal 'quarantined', state(generation)['status']
    calls = @api.calls
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal calls, @api.calls
  end
  def test_two_cooperating_publishers_have_one_revision_winner
    generations = [ready(1), ready(2)]
    gate_read, gate_write = IO.pipe
    result_read, result_write = IO.pipe
    pids = generations.map do |generation|
      fork do
        gate_write.close; result_read.close
        gate_read.read(1)
        begin
          reopen.promote(generation)
          result_write.puts('promoted')
        rescue CatalogGeneration::Unsafe
          result_write.puts('stale')
        end
        result_write.close
        exit!(0)
      end
    end
    gate_read.close; result_write.close
    gate_write.write('xx'); gate_write.close
    outcomes = Timeout.timeout(5) { result_read.read.lines.map(&:strip) }
    pids.each { |pid| assert_equal 0, Process.wait2(pid).last.exitstatus }
    assert_equal %w[promoted stale], outcomes.sort
    assert_equal 1, reopen.pointer['revision']
    assert_includes generations, reopen.pointer['active']
  ensure
    [gate_read, gate_write, result_read, result_write].compact.each { |io| io.close unless io.closed? }
    (pids || []).each do |pid|
      begin
        if Process.waitpid(pid, Process::WNOHANG).nil?
          Process.kill('KILL', pid)
          Process.waitpid(pid)
        end
      rescue Errno::ECHILD, Errno::ESRCH
        # Already reaped or exited.
      end
    end
  end

  def test_exit_after_acceptance_before_ack_does_not_dispatch_again
    generation = @store.stage(snapshot(1))
    pid = fork do
      @api.fault = :exit_after_accept
      reopen.ingest(generation, batch_id: 'one', record_ids: [1])
      exit!(99)
    end
    _, status = Timeout.timeout(5) { Process.wait2(pid) }
    assert_equal 84, status.exitstatus
    assert_equal 1, @api.calls
    assert_equal 1, @api.rows.fetch(generation).length
    assert_equal 'in_flight', state(generation)['batches']['one']['status']
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal 1, @api.calls
    assert_equal 'quarantined', state(generation)['status']
    assert_nil reopen.pointer['active']
  ensure
    begin
      if pid && Process.waitpid(pid, Process::WNOHANG).nil?
        Process.kill('KILL', pid); Process.waitpid(pid)
      end
    rescue Errno::ECHILD, Errno::ESRCH
    end
  end

  def test_exit_after_acknowledgement_save_reuses_ack_without_dispatch
    generation = @store.stage(snapshot(1))
    interrupted(generation, :after_ack, 85)
    assert_equal 1, @api.calls
    assert_equal 'acknowledged', state(generation)['batches']['one']['status']
    assert_equal({'accepted' => 1, 'rejected' => 0}, reopen.ingest(generation, batch_id: 'one', record_ids: [1]))
    assert_equal 1, @api.calls
    assert_equal generation, reopen.promote(generation)
  end

  def test_uncertain_batch_blocks_a_disjoint_batch
    manifest = snapshot(1)
    manifest[:snapshots][0][:offers] << {offer_id: 'two', record_id: 2, smiles: 'CCO'}
    generation = @store.stage(manifest)
    interrupted(generation, :before_dispatch, 83)
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'two', record_ids: [2]) }
    assert_equal 0, @api.calls
    assert_equal 'quarantined', state(generation)['status']
  end
  def test_missing_acceptance_count_quarantines
    generation = @store.stage(snapshot(1))
    @api.fault = :missing_count
    assert_raises(CatalogGeneration::Unsafe) { @store.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_equal 1, @api.rows.fetch(generation).length
    assert_raises(CatalogGeneration::Unsafe) { reopen.promote(generation) }
    assert_equal 'quarantined', state(generation)['status']
  end
  def test_lost_create_ack_does_not_reuse_uncertain_index
    @api.fault = :lost_create_ack
    assert_raises(IOError) { @store.stage(snapshot(1)) }
    generation = @api.rows.keys.fetch(0)
    assert_equal 'quarantined', state(generation)['status']
    assert_raises(CatalogGeneration::Unsafe) { reopen.ingest(generation, batch_id: 'one', record_ids: [1]) }
    assert_nil reopen.pointer['active']
    @api.fault = nil
    replacement = @store.stage(snapshot(1))
    refute_equal generation, replacement
    assert_equal 2, @api.rows.length
  end
  def test_interrupted_rollback_does_not_toggle_twice
    first = ready(1); @store.promote(first)
    second = ready(2); @store.promote(second)
    before = @store.pointer
    pid = fork do
      journal = reopen(ExitingJournal); journal.exit_at = :after_pointer
      journal.rollback(expected_revision: before['revision'])
      exit!(99)
    end
    assert_equal 82, Timeout.timeout(5) { Process.wait2(pid).last.exitstatus }
    after = reopen.pointer
    assert_equal first, after['active']
    assert_equal before['revision'] + 1, after['revision']
    assert_equal before['high_water'], after['high_water']
    assert_raises(CatalogGeneration::Unsafe) { reopen.rollback(expected_revision: before['revision']) }
    assert_equal after, reopen.pointer
  ensure
    begin
      if pid && Process.waitpid(pid, Process::WNOHANG).nil?
        Process.kill('KILL', pid); Process.waitpid(pid)
      end
    rescue Errno::ECHILD, Errno::ESRCH
    end
  end

end
