# frozen_string_literal: true
# AI-assisted acceptance harness. Uses the exact artifact-installed SDK/importer.
require 'json'
require 'digest'
require 'delegate'
require 'timeout'
source = ENV.fetch('PILOT_SOURCE')
require File.join(source, 'sdk/ruby/examples/catalog_generation')
require File.join(source, 'sdk/ruby/examples/catalog_installed_sdk_check')
require File.join(source, 'sdk/ruby/examples/catalog_native_oracle')

class FaultPeer < SimpleDelegator
  attr_accessor :fault
  def ingest(index, body, **options)
    case fault
    when 'duplicate_omit'
      rows = body.lines
      rows[-1] = rows.first
      body = rows.join
    when 'partial'
      body += JSON.generate(record_id: 'invalid-u64', smiles: 'CC') + "\n"
    end
    response = __getobj__.ingest(index, body, **options)
    raise IOError, 'injected lost acknowledgement AFTER real acceptance' if fault == 'lost_ack'
    response
  end
end

def canonical(value)
  case value
  when Hash then value.sort.to_h.transform_values { |v| canonical(v) }
  when Array then value.map { |v| canonical(v) }
  else value
  end
end

def reject!
  begin
    yield
  rescue CatalogGeneration::Unsafe, IOError
    return
  end
  raise 'required rejection did not happen'
end

class Acceptance
  def initialize
    CatalogInstalledSdkCheck.verify!(spec: Gem.loaded_specs.fetch('quickwit-cheminee'), features: $LOADED_FEATURES)
    config = QuickwitCheminee::Configuration.new
    config.scheme, config.host, config.base_path, config.timeout = 'http', ENV.fetch('SDK_SMOKE_HOST'), '', 300
    @api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
    @peer = FaultPeer.new(@api)
    @work = ENV.fetch('CATALOG_WORK')
    @rows = File.foreach(ENV.fetch('CATALOG_CORPUS')).map { |line| JSON.parse(line) }
    raise '100k corpus membership differs' unless @rows.length == 100_000 && @rows.map { |r| r['record_id'] }.uniq.length == 100_000
    @suppliers = @rows.map { |r| r.fetch('supplier') }.uniq.sort
    @options = { api: @peer, directory: File.join(@work, 'journal'), expected_suppliers: @suppliers,
                 native_preparation: { spec: CatalogGeneration::NativePreparation::SPEC, prepared_smiles_field: 'prepared_smiles' },
                 index_heap_size_bytes: 128 * 1024 * 1024 }
  end

  def manifest(rows, sequence)
    { suppliers: @suppliers, snapshots: @suppliers.map do |supplier|
      selected = rows.select { |r| r['supplier'] == supplier }
      { supplier: supplier, sequence: sequence, complete: true,
        observed_at: selected.first.fetch('observed_at'), offers: selected }
    end }
  end

  def import(store, rows, sequence)
    generation = store.stage(manifest(rows, sequence))
    reject! { store.promote(generation) } # Publication before acknowledgement is forbidden.
    rows.map { |r| r['record_id'] }.each_slice(1000).with_index do |ids, batch|
      ack = store.ingest(generation, batch_id: "batch-#{batch}", record_ids: ids)
      raise 'partial acceptance' unless ack == { 'accepted' => ids.length, 'rejected' => 0 }
      puts JSON.generate(event: 'ingest', generation: generation, batch: batch, ack: ack)
    end
    store.promote(generation) # Complete partitioned source/membership/native-field audit.
    generation
  end

  def export(store, name)
    pointer = store.verify_active
    state = JSON.parse(File.read(File.join(@work, 'journal', pointer.fetch('active') + '.json')))
    exact = QuickwitCheminee::ExactSearch.new(api: @api, generation: pointer.fetch('active'))
    destination = File.join(@work, "#{name}.ndjson")
    ids = []
    File.open(destination, 'w') do |file|
      state.fetch('records').each_slice(5000) do |partition|
        range = { range: { record_id: { gte: partition.first['record_id'], lte: partition.last['record_id'] } } }
        partition.each_slice(100).with_index do |expected, page|
          result = exact.search(query: range, limit: expected.length, offset: page * 100, order: :record_id)
          raise 'export count mismatch' unless result[:hits][:total][:value] == partition.length
          result[:hits][:hits].zip(expected).each do |hit, row|
            actual = JSON.parse(JSON.generate(hit.fetch(:_source)))
            raise 'export identity mismatch' unless actual['record_id'] == row['record_id']
            ids << actual['record_id']
            file.puts JSON.generate(canonical(actual))
          end
        end
      end
    end
    raise 'export omitted/duplicated records' unless ids == state['records'].map { |r| r['record_id'] }
    { pointer: pointer, records: ids.length, source_sha256: Digest::SHA256.file(destination).hexdigest }
  end

  def negatives(store)
    before = store.pointer
    small = @suppliers.flat_map { |s| @rows.select { |r| r['supplier'] == s }.first(2) }
    incomplete = manifest(small, 3)
    incomplete[:snapshots][0][:complete] = false
    reject! { store.stage(incomplete) }
    %w[partial lost_ack duplicate_omit invalid_smiles].each do |fault|
      records = Marshal.load(Marshal.dump(small))
      records[0]['smiles'] = 'not-a-smiles' if fault == 'invalid_smiles'
      generation = store.stage(manifest(records, 3))
      @peer.fault = fault
      if fault == 'duplicate_omit'
        store.ingest(generation, batch_id: fault, record_ids: records.map { |r| r['record_id'] })
        reject! { store.promote(generation) }
      else
        reject! { store.ingest(generation, batch_id: fault, record_ids: records.map { |r| r['record_id'] }) }
        reject! { store.promote(generation) }
      end
      @peer.fault = nil
      state = JSON.parse(File.read(File.join(@work, 'journal', generation + '.json')))
      raise 'uncertain/partial generation not quarantined' unless state['status'] == 'quarantined'
      raise 'failed import changed published pointer' unless store.pointer == before
    end
    reject! { store.stage(manifest(@rows, 1)) }
    { mixed_rejection: true, lost_ack_after_dispatch: true, duplicate_omit_audited: true,
      invalid_smiles: true, incomplete_snapshot: true, stale_sequence: true }
  end

  def curated
    oracle = CatalogNativeOracle.new(@api, oracle_path: ENV.fetch('CATALOG_NATIVE_ORACLE'))
    rows = oracle.fixtures.each_with_index.map do |fixture, i|
      { offer_id: "curated-#{i}", record_id: i + 1, smiles: fixture['smiles'], extra_data: fixture['extra_data'], sample: true }
    end
    options = @options.merge(api: oracle, directory: File.join(@work, 'curated'), expected_suppliers: ['curated'])
    store = CatalogGeneration.create(**options)
    generation = store.stage({suppliers: ['curated'], snapshots: [{supplier: 'curated', sequence: 1,
      complete: true, observed_at: '2026-10-23T00:00:00Z', offers: rows}]})
    store.ingest(generation, batch_id: 'curated', record_ids: (1..20).to_a)
    store.promote(generation)
    checks = oracle.verify_queries!(generation, (1..20).to_a)
    # The declared tautomer profile removes lactate's tautomer-sensitive stereo;
    # the retained native golden explicitly contains CC(O)C(=O)O.
    [['C[C@H](O)C(=O)O', true, [4]], ['C[C@@H](O)C(=O)O', true, [4]],
     ['C[C@@H](O)C(=O)O', false, [4]], ['[13CH3]CO', true, []],
     ['[Na+].CC(=O)[O-]', true, [3]]].each do |smiles, chirality, ids|
      request = QuickwitCheminee::GraphSearchRequest.new(spec: QuickwitCheminee::FingerprintSpec.new(CatalogGeneration::NativePreparation::SPEC),
        smiles: smiles, use_chirality: chirality, include_identity: true, ranking: 'stable_id',
        result_limit: 100, prepared_smiles_field: 'prepared_smiles')
      response = @api.cheminee_v1_identity(generation, request)
      raise 'curated chirality/isotope/salt identity failed' unless response.num_hits == ids.length && response.hits.map { |h| h.record_id.to_i } == ids
    end
    stable = CatalogGeneration.create(**@options.merge(directory: File.join(@work, 'stereo'), expected_suppliers: ['stereo']))
    stable_rows = ['C[C@H](F)Cl', 'C[C@@H](F)Cl', '[13CH3]CO', 'CCO'].each_with_index.map do |smiles, i|
      { offer_id: "stereo-#{i}", record_id: i + 1, smiles: smiles }
    end
    stable_index = stable.stage({suppliers: ['stereo'], snapshots: [{supplier: 'stereo', sequence: 1,
      complete: true, observed_at: '2026-10-23T00:00:00Z', offers: stable_rows}]})
    stable.ingest(stable_index, batch_id: 'stereo', record_ids: [1, 2, 3, 4])
    stable.promote(stable_index)
    [['C[C@H](F)Cl', true, [1]], ['C[C@@H](F)Cl', true, [2]],
     ['C[C@H](F)Cl', false, [1, 2]], ['[13CH3]CO', true, [3]]].each do |smiles, chirality, ids|
      request = QuickwitCheminee::GraphSearchRequest.new(spec: QuickwitCheminee::FingerprintSpec.new(CatalogGeneration::NativePreparation::SPEC),
        smiles: smiles, use_chirality: chirality, include_identity: true, ranking: 'stable_id',
        result_limit: 100, prepared_smiles_field: 'prepared_smiles')
      response = @api.cheminee_v1_identity(stable_index, request)
      raise 'stable stereocenter/isotope identity failed' unless response.num_hits == ids.length && response.hits.map { |h| h.record_id.to_i } == ids
    end
    checks.merge(chirality_isotope_salt_cases: 9, tautomer_sensitive_stereo_removed: true)
  end

  def run(phase)
    case phase
    when 'create'
      store = CatalogGeneration.create(**@options)
      import(store, @rows, 1)
      result = export(store, 'initial')
      result[:negative_cases] = negatives(store)
      result[:curated_native_queries] = curated
      File.write(File.join(@work, 'initial-receipt.json'), JSON.generate(result))
      result
    when 'refresh'
      store = CatalogGeneration.new(**@options)
      changed = Marshal.load(Marshal.dump(@rows))
      changed[0]['revision_marker'] = 'updated'
      removed = changed.pop
      changed << removed.merge('record_id' => 100_001, 'offer_id' => 'synthetic-refresh-addition', 'smiles' => 'CCO')
      old = store.pointer.fetch('active')
      import(store, changed, 2)
      raise 'refresh lost rollback target' unless store.pointer['previous'] == old
      result = export(store, 'refreshed')
      File.write(File.join(@work, 'refreshed-receipt.json'), JSON.generate(result))
      result
    when 'verify', 'restored'
      store = CatalogGeneration.new(**@options)
      result = export(store, phase)
      receipt = JSON.parse(File.read(File.join(@work, 'refreshed-receipt.json')))
      raise 'restart/restore source or pointer differs' unless JSON.parse(JSON.generate(result)) == receipt
      result
    when 'rollback'
      store = CatalogGeneration.new(**@options)
      before = store.pointer
      store.rollback(expected_revision: before['revision'])
      result = export(store, 'rolled-back')
      initial = JSON.parse(File.read(File.join(@work, 'initial-receipt.json')))
      raise 'rollback data mismatch' unless result[:source_sha256] == initial['source_sha256']
      raise 'rollback high water changed' unless store.pointer['high_water'] == before['high_water']
      result
    else raise 'unknown phase'
    end
  end
end

phase = ARGV.fetch(0)
started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
result = Timeout.timeout(2700) { Acceptance.new.run(phase) }
File.write(ENV.fetch('PHASE_RESULT'), JSON.pretty_generate(result.merge(status: 'passed', phase: phase,
  seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - started, sdk: QuickwitCheminee::VERSION)))
