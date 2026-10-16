# frozen_string_literal: true
require 'tmpdir'
require 'delegate'
require_relative 'catalog_generation'

class InjectedClient < SimpleDelegator
  attr_accessor :fault
  attr_reader :created, :ingest_calls
  def initialize(api)
    super(api)
    @created = []
    @ingest_calls = 0
  end
  def create_index(mapping, **options)
    @created << mapping.fetch(:index_id)
    __getobj__.create_index(mapping, **options)
  end
  def ingest(index, body, **options)
    @ingest_calls += 1
    case fault
    when :interrupt_before_dispatch
      exit!(88) # Journal has already fsynced in_flight; no request was sent.
    when :duplicate_and_omit
      rows = body.lines
      rows[-1] = rows.first
      body = rows.join
    when :mixed_reject
      body += JSON.generate(record_id: 'not-a-u64') + "\n"
    end
    result = __getobj__.ingest(index, body, **options)
    raise IOError, 'injected acknowledgement loss after server response' if fault == :lose_ack
    result
  end
end

class InterruptedPromotion < CatalogGeneration
  private
  def save(name, value)
    super
    exit!(89) if name == 'active.json'
  end
end

def manifest(sequence, changed: false)
  { suppliers: %w[Acme Beta], snapshots: [
    { supplier: 'Acme', sequence: sequence, complete: true, observed_at: '2026-10-16T12:00:00Z', offers: [
      { offer_id: 'a1', record_id: 1, smiles: 'C[C@H](O)Cl', price: changed ? 12 : 10 },
      *(!changed ? [{ offer_id: 'a2', record_id: 2, smiles: 'CCO.Cl', price: 20 }] : [])
    ] },
    { supplier: 'Beta', sequence: sequence, complete: true, observed_at: '2026-10-16T12:01:00Z', offers: [
      { offer_id: 'b1', record_id: 3, smiles: 'C[C@H](O)Cl', price: 15 }
    ] }
  ] }
end

def rejected(label)
  begin
    yield
  rescue CatalogGeneration::Unsafe, IOError
    return label
  end
  raise "Expected rejection: #{label}"
end

config = QuickwitCheminee::Configuration.new
config.scheme = 'http'
config.host = ENV.fetch('SDK_SMOKE_HOST', '127.0.0.1:19480')
config.base_path = ''
config.timeout = 30
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
client = InjectedClient.new(api)
checks = []
Dir.mktmpdir('catalog-generation-') do |directory|
  store = CatalogGeneration.new(api: client, directory: directory, expected_suppliers: %w[Acme Beta])
  begin
    first = store.stage(manifest(1))
    ack = store.ingest(first, batch_id: 'batch-1', record_ids: [1, 2, 3])
    calls = client.ingest_calls
    raise 'duplicate batch changed acknowledgement' unless store.ingest(first, batch_id: 'batch-1', record_ids: [1, 2, 3]) == ack
    raise 'duplicate batch dispatched again' unless client.ingest_calls == calls
    checks << 'duplicate batch returns journal acknowledgement without HTTP'
    checks << rejected('float record ID cannot bypass overlap guard') { store.ingest(first, batch_id: 'float', record_ids: [1.0]) }
    checks << rejected('batch ID/content conflict') { store.ingest(first, batch_id: 'batch-1', record_ids: [1]) }
    store.promote(first)
    initial = store.pointer
    partial = manifest(2)
    partial[:snapshots][0][:complete] = false
    checks << rejected('partial scrape cannot withdraw offers') { store.stage(partial) }
    raise 'partial scrape changed active generation' unless store.pointer == initial

    %i[lose_ack mixed_reject duplicate_and_omit].each do |fault|
      candidate = store.stage(manifest(2))
      client.fault = fault
      if fault == :duplicate_and_omit
        store.ingest(candidate, batch_id: 'batch-1', record_ids: [1, 2, 3])
        checks << rejected('same count duplicate/missing content cannot promote') { store.promote(candidate) }
      else
        checks << rejected("#{fault} quarantines staging") { store.ingest(candidate, batch_id: 'batch-1', record_ids: [1, 2, 3]) }
        client.fault = nil
        restarted = CatalogGeneration.new(api: client, directory: directory, expected_suppliers: %w[Acme Beta])
        before = client.ingest_calls
        checks << rejected("#{fault} cannot replay after importer restart") { restarted.ingest(candidate, batch_id: 'batch-1', record_ids: [1, 2, 3]) }
        raise 'uncertain batch replayed' unless client.ingest_calls == before
      end
      client.fault = nil
      raise 'failed candidate changed active generation' unless store.pointer == initial
    end

    interrupted = store.stage(manifest(2))
    pid = fork do
      client.fault = :interrupt_before_dispatch
      store.ingest(interrupted, batch_id: 'batch-1', record_ids: [1, 2, 3])
    end
    _, status = Process.wait2(pid)
    raise 'wrong interruption point' unless status.exitstatus == 88
    checks << rejected('in-flight journal survives process interruption') do
      CatalogGeneration.new(api: client, directory: directory, expected_suppliers: %w[Acme Beta]).ingest(interrupted, batch_id: 'batch-1', record_ids: [1, 2, 3])
    end
    raise 'interruption changed active generation' unless store.pointer == initial

    second = store.stage(manifest(2, changed: true))
    store.ingest(second, batch_id: 'batch-1', record_ids: [1, 3])
    store.promote(second)
    checks << 'complete refresh changes price and withdraws only the missing offer'
    checks << rejected('out-of-order sequence') { store.stage(manifest(1)) }
    a = store.stage(manifest(3, changed: true))
    b = store.stage(manifest(4, changed: true))
    [a, b].each { |generation| store.ingest(generation, batch_id: 'batch-1', record_ids: [1, 3]) }
    store.promote(a)
    checks << rejected('stale concurrent promotion loses revision comparison') { store.promote(b) }
    current = store.pointer
    raise 'rollback target differs' unless store.rollback(expected_revision: current['revision']) == second
    raise 'rollback moved source high-water backwards' unless store.pointer['high_water'] == current['high_water']
    checks << rejected('rollback revision conflict') { store.rollback(expected_revision: current['revision']) }
    checks << rejected('rollback cannot enable stale source replay') { store.stage(manifest(3)) }
    changed_id = manifest(5)
    changed_id[:snapshots][0][:offers][0][:record_id] = 9
    checks << rejected('stable offer cannot acquire a different record ID') { store.stage(changed_id) }
    recycled = manifest(5)
    recycled[:snapshots][0][:offers][1][:offer_id] = 'replacement-offer'
    checks << rejected('withdrawn record ID cannot be recycled') { store.stage(recycled) }
    recovery = store.stage(manifest(5, changed: true))
    store.ingest(recovery, batch_id: 'batch-1', record_ids: [1, 3])
    pid = fork do
      InterruptedPromotion.new(api: client, directory: directory, expected_suppliers: %w[Acme Beta]).promote(recovery)
    end
    _, status = Process.wait2(pid)
    raise 'wrong publication interruption point' unless status.exitstatus == 89
    published = store.pointer
    raise 'pointer was not published' unless published['active'] == recovery
    before = client.ingest_calls
    raise 'publication retry failed' unless store.promote(recovery) == recovery
    raise 'publication retry changed revision or high-water' unless store.pointer == published
    raise 'publication retry dispatched a write' unless client.ingest_calls == before
    checks << 'process exit after pointer fsync recovers publication idempotently'
    larger = manifest(6, changed: true)
    larger[:snapshots][0][:offers] = (1000...1120).map { |id| { offer_id: "large-#{id}", record_id: id, smiles: 'CCO' } }
    large = store.stage(larger)
    store.ingest(large, batch_id: 'batch-1', record_ids: [3] + (1000...1120).to_a)
    store.promote(large)
    checks << 'content audit traverses multiple 100-document pages'
    empty = manifest(7)
    empty[:snapshots].each { |snapshot| snapshot[:offers] = [] }
    zero = store.stage(empty)
    store.promote(zero)
    raise 'empty snapshot rollback failed' unless store.rollback(expected_revision: store.pointer['revision']) == large
    checks << 'explicit complete empty catalog promotes and rolls back'
    checks << 'rollback validates retained content and preserves source high-water'
    puts JSON.generate(status: 'passed', checks: checks, scope: 'single-host sole-writer generation journal over real HTTP; no HA or server write fence')
  ensure
    client.created.each { |generation| api.delete_index(generation) }
  end
end
