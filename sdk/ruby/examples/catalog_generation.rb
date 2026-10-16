# frozen_string_literal: true

# Single-host importer example, outside the gem. All writers must use this journal.
# It is not a server alias, distributed lock, durable write fence, or exactly-once API.
require 'json'
require 'digest'
require 'fileutils'
require 'securerandom'
require 'time'
gem 'quickwit-cheminee', ENV.fetch('SDK_EXPECTED_VERSION', '0.9.1.pre.contract1')
require 'quickwit-cheminee'
require 'quickwit-cheminee/exact_search'

class CatalogGeneration
  class Unsafe < StandardError; end
  MAX_AUDIT_DOCS = 10_000 # Current ExactSearch offset safety bound, not a tuning recommendation.

  def initialize(api:, directory:, expected_suppliers:)
    @api = api
    @directory = File.expand_path(directory)
    raise Unsafe, 'invalid supplier scope' unless expected_suppliers.is_a?(Array) && !expected_suppliers.empty? && expected_suppliers.all? { |s| s.is_a?(String) && !s.empty? }
    @suppliers = expected_suppliers.map { |name| name.dup.freeze }.sort.freeze
    raise Unsafe, 'duplicate supplier scope' unless @suppliers.uniq == @suppliers
    unless File.directory?(@directory)
      Dir.mkdir(@directory, 0o700) # Parent must already exist.
      File.open(File.dirname(@directory), File::RDONLY) { |parent| parent.fsync }
    end
    locked do
      scope = read('scope.json')
      raise Unsafe, 'supplier scope changed' if scope && scope['suppliers'] != @suppliers
      save('scope.json', { 'suppliers' => @suppliers }) unless scope
    end
  end

  def pointer
    locked { read('active.json') || { 'revision' => 0, 'active' => nil, 'previous' => nil, 'high_water' => {} } }
  end

  # manifest: {suppliers: [names], snapshots: [{supplier:, sequence:, complete:,
  # observed_at:, offers: [{offer_id:, record_id:, smiles:, ...}]}]}
  # Do not manufacture `complete: true` from a successful HTTP scrape request.
  def stage(manifest)
    normalized = JSON.parse(JSON.generate(manifest))
    suppliers = normalized.fetch('suppliers').sort
    snapshots = normalized.fetch('snapshots')
    raise Unsafe, 'supplier coverage mismatch' unless suppliers == @suppliers && snapshots.map { |s| s.fetch('supplier') }.sort == suppliers
    raise Unsafe, 'incomplete snapshot' unless snapshots.all? { |s| s['complete'] == true && s['sequence'].is_a?(Integer) && s['sequence'] >= 0 }
    records = snapshots.flat_map do |snapshot|
      observed = Time.iso8601(snapshot.fetch('observed_at')).utc.iso8601
      snapshot.fetch('offers').map do |offer|
        raise Unsafe, 'invalid offer identity' unless offer['offer_id'].is_a?(String) && !offer['offer_id'].empty?
        raise Unsafe, 'invalid structure' unless offer['smiles'].is_a?(String) && !offer['smiles'].empty?
        raise Unsafe, 'invalid record_id' unless offer['record_id'].is_a?(Integer) && (0..((1 << 64) - 1)).cover?(offer['record_id'])
        offer.merge('supplier' => snapshot['supplier'], 'observed_at' => observed)
      end
    end
    raise Unsafe, 'audit exceeds tested offset boundary' if records.length > MAX_AUDIT_DOCS
    raise Unsafe, 'duplicate record_id' unless records.map { |r| r['record_id'] }.uniq.length == records.length
    raise Unsafe, 'duplicate offer identity' unless records.map { |r| r.values_at('supplier', 'offer_id') }.uniq.length == records.length
    sequences = snapshots.to_h { |s| [s['supplier'], s['sequence']] }
    locked do
      active = read('active.json') || { 'revision' => 0, 'active' => nil, 'previous' => nil, 'high_water' => {} }
      raise Unsafe, 'stale source sequence' if sequences.any? { |supplier, sequence| sequence <= active['high_water'].fetch(supplier, -1) }
      identities = read('identities.json') || { 'offers' => {}, 'records' => {} }
      records.each do |record|
        key = JSON.generate(record.values_at('supplier', 'offer_id'))
        id = record['record_id']
        old_id = identities['offers'][key]
        old_offer = identities['records'][id.to_s]
        raise Unsafe, 'offer record_id changed' if old_id && old_id != id
        raise Unsafe, 'record_id recycled' if old_offer && old_offer != key
        identities['offers'][key] = id
        identities['records'][id.to_s] = key
      end
      # Reservations survive failed staging, withdrawals and rollback; IDs are never recycled.
      save('identities.json', identities)
      generation = "offers-#{SecureRandom.hex(12)}"
      state = { 'generation' => generation, 'status' => 'creating', 'base_revision' => active['revision'],
                'sequences' => sequences, 'records' => records.sort_by { |r| r['record_id'] }, 'batches' => {} }
      save("#{generation}.json", state)
      begin
        @api.create_index(mapping(generation), overwrite: false)
        state['status'] = 'staging'
        save("#{generation}.json", state)
      rescue StandardError
        state['status'] = 'quarantined'
        state['quarantine_reason'] ||= 'write acknowledgement or journal outcome unknown'
        save("#{generation}.json", state)
        raise
      end
      generation
    end
  end

  def ingest(generation, batch_id:, record_ids:)
    locked do
      state = generation_state(generation)
      raise Unsafe, 'generation is not writable' unless state['status'] == 'staging'
      quarantine(state, 'uncertain batch on recovery') if state['batches'].values.any? { |b| b['status'] == 'in_flight' }
      raise Unsafe, 'invalid batch ID' unless batch_id.is_a?(String) && !batch_id.empty?
      raise Unsafe, 'invalid batch record IDs' unless record_ids.is_a?(Array)
      record_ids = record_ids.dup.freeze
      raise Unsafe, 'invalid batch record IDs' unless record_ids.all? { |id| id.is_a?(Integer) && (0..((1 << 64) - 1)).cover?(id) }
      records = state['records'].select { |r| record_ids.include?(r['record_id']) }
      raise Unsafe, 'invalid batch membership' unless record_ids.uniq.length == record_ids.length && records.length == record_ids.length && !records.empty?
      digest = Digest::SHA256.hexdigest(JSON.generate(records))
      old = state['batches'][batch_id]
      if old
        raise Unsafe, 'batch ID reused with different content' unless old['digest'] == digest
        return old['ack'] if old['status'] == 'acknowledged'
        quarantine(state, 'uncertain previous batch')
      end
      prior_ids = state['batches'].values.flat_map { |b| b['record_ids'] }
      raise Unsafe, 'records already assigned to another batch' unless (prior_ids & record_ids).empty?
      batch = { 'digest' => digest, 'record_ids' => record_ids, 'status' => 'in_flight' }
      state['batches'][batch_id] = batch
      save("#{generation}.json", state) # fsync before dispatch; crash here requires quarantine.
      begin
        response = @api.ingest(generation, records.map { |r| JSON.generate(r) }.join("\n") + "\n",
                               commit: 'wait_for', detailed_response: true)
        unless response.num_ingested_docs == records.length && response.num_rejected_docs == 0
          quarantine(state, 'partial or unknown acceptance')
        end
        batch['ack'] = { 'accepted' => response.num_ingested_docs, 'rejected' => response.num_rejected_docs }
        batch['status'] = 'acknowledged'
        save("#{generation}.json", state)
        batch['ack']
      rescue StandardError
        state['status'] = 'quarantined'
        state['quarantine_reason'] ||= 'write acknowledgement or journal outcome unknown'
        save("#{generation}.json", state)
        raise
      end
    end
  end

  def promote(generation)
    locked do
      state = generation_state(generation)
      active = read('active.json') || { 'revision' => 0, 'active' => nil, 'previous' => nil, 'high_water' => {} }
      # The fsynced pointer is authoritative after an interrupted publication.
      if active['active'] == generation && %w[sealed promoted].include?(state['status'])
        state['status'] = 'promoted'
        save("#{generation}.json", state)
        return generation
      end
      quarantine(state, 'uncertain batch on recovery') if state['batches'].values.any? { |b| b['status'] != 'acknowledged' }
      raise Unsafe, 'generation is not promotable' unless %w[staging sealed].include?(state['status'])
      assigned = state['batches'].values.flat_map { |b| b['record_ids'] }.sort
      raise Unsafe, 'not all records acknowledged' unless assigned == state['records'].map { |r| r['record_id'] }
      # Sole-writer lock prevents this importer from appending while auditing.
      begin
        audit(state)
      rescue StandardError
        quarantine(state, 'generation audit failed')
      end
      active = read('active.json') || { 'revision' => 0, 'active' => nil, 'previous' => nil, 'high_water' => {} }
      raise Unsafe, 'activation revision changed; build a fresh generation' unless active['revision'] == state['base_revision']
      raise Unsafe, 'stale source sequence' if state['sequences'].any? { |s, n| n <= active['high_water'].fetch(s, -1) }
      state['status'] = 'sealed'
      save("#{generation}.json", state)
      save('active.json', { 'revision' => active['revision'] + 1, 'active' => generation, 'previous' => active['active'],
                            'high_water' => active['high_water'].merge(state['sequences']) })
      state['status'] = 'promoted'
      save("#{generation}.json", state)
      generation
    end
  end

  def rollback(expected_revision:)
    locked do
      active = read('active.json') || raise(Unsafe, 'no active generation')
      raise Unsafe, 'activation revision changed' unless active['revision'] == expected_revision
      previous = active['previous'] || raise(Unsafe, 'no retained rollback generation')
      audit(generation_state(previous))
      save('active.json', active.merge('revision' => active['revision'] + 1,
                                      'active' => previous, 'previous' => active['active']))
      previous # High-water sequences deliberately do not roll back.
    end
  end

  private

  def mapping(generation)
    { version: '0.9', index_id: generation, doc_mapping: { mode: 'dynamic',
      dynamic_mapping: { stored: true }, field_mappings: [{ name: 'record_id', type: 'u64', fast: true, stored: true }] },
      indexing_settings: { commit_timeout_secs: 1 } }
  end

  def audit(state)
    exact = QuickwitCheminee::ExactSearch.new(api: @api, generation: state['generation'])
    query = { match_all: {} }
    raise Unsafe, 'published count mismatch' unless exact.count(query: query) == state['records'].length
    actual = (0...state['records'].length).step(100).flat_map do |offset|
      exact.search(query: query, limit: [100, state['records'].length - offset].min, offset: offset)[:hits][:hits].map { |hit| JSON.parse(JSON.generate(hit[:_source])) }
    end
    raise Unsafe, 'offer membership or contents differ' unless actual == state['records']
  end

  def generation_state(generation)
    raise Unsafe, 'invalid generation name' unless /\Aoffers-[0-9a-f]{24}\z/.match?(generation)
    read("#{generation}.json") || raise(Unsafe, 'unknown generation')
  end

  def quarantine(state, reason)
    state['status'] = 'quarantined'
    state['quarantine_reason'] = reason
    save("#{state['generation']}.json", state)
    raise Unsafe, reason
  end

  def locked
    File.open(File.join(@directory, 'writer.lock'), File::RDWR | File::CREAT, 0o600) do |lock|
      lock.flock(File::LOCK_EX)
      yield
    end
  end

  def read(name)
    path = File.join(@directory, name)
    File.file?(path) ? JSON.parse(File.read(path)) : nil
  end

  def save(name, value)
    target = File.join(@directory, name)
    temporary = "#{target}.#{SecureRandom.hex(6)}.tmp"
    File.open(temporary, File::WRONLY | File::CREAT | File::EXCL, 0o600) do |file|
      file.write(JSON.generate(value)); file.flush; file.fsync
    end
    File.rename(temporary, target)
    File.open(@directory, File::RDONLY) { |directory| directory.fsync }
  ensure
    File.unlink(temporary) if temporary && File.file?(temporary)
  end
end
