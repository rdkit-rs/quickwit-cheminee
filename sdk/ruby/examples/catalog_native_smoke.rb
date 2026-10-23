# frozen_string_literal: true

# Real HTTP acceptance over 10,001 synthetic offers repeating 20 small structures.
# This is not representative-catalog, 100k, kind/S3, performance or durability proof.
require 'timeout'
require_relative 'catalog_generation'
require_relative 'catalog_native_oracle'
require_relative 'catalog_installed_sdk_check'
require_relative '../loaded_json_check'

class CatalogNativeSmoke
  COUNT = 10_001
  HEAP_BYTES = 32 * 1024 * 1024 # Bounded acceptance parameter, not measured sizing advice.

  def initialize
    verify_installed_code!
    config = QuickwitCheminee::Configuration.new
    config.scheme = 'http'
    config.host = ENV.fetch('SDK_SMOKE_HOST')
    config.base_path = ''
    config.timeout = 60
    api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
    raise 'native server is not ready' unless api.ready
    @oracle = CatalogNativeOracle.new(api, oracle_path: ENV.fetch('CATALOG_NATIVE_ORACLE'))
    @directory = File.expand_path(ENV.fetch('CATALOG_NATIVE_STATE'))
    @ids = [0] + (1...COUNT - 1).map { |ordinal| (1 << 53) + ordinal * 97 } + [(1 << 64) - 1]
    @options = { api: @oracle, directory: File.join(@directory, 'journal'), expected_suppliers: %w[Acme Beta],
                 native_preparation: { spec: CatalogGeneration::NativePreparation::SPEC, prepared_smiles_field: 'prepared_smiles' },
                 index_heap_size_bytes: HEAP_BYTES }
  end

  def run
    phase = ENV.fetch('CATALOG_NATIVE_PHASE', 'create')
    result = case phase
             when 'create' then create
             when 'verify' then verify
             when 'restored' then verify_restored
             else raise 'unknown native catalog acceptance phase'
             end
    puts JSON.generate(result.merge(status: 'passed', phase: phase, installed_gem: QuickwitCheminee::VERSION,
      ruby: RUBY_VERSION, json: JSON::VERSION, synthetic_offers: COUNT, unique_input_structures: 20,
      cheminee_golden_structures: 8, source_comparisons: @oracle.checked_sources, index_heap_size_bytes: HEAP_BYTES,
      scope: 'single-node HTTP synthetic partition boundary and native mapping/facade acceptance; no 100k/kind/object-store/performance claim'))
  end

  private

  def verify_installed_code!
    CatalogInstalledSdkCheck.verify!(spec: Gem.loaded_specs.fetch('quickwit-cheminee'), features: $LOADED_FEATURES)
    LoadedJsonCheck.verify!(spec: Gem.loaded_specs.fetch('json'), version: JSON::VERSION, features: $LOADED_FEATURES)
  end

  def manifest(sequence, refresh: false)
    count = refresh ? COUNT - 1 : COUNT
    offers = (0...count).map do |ordinal|
      fixture = @oracle.fixtures.fetch(ordinal % 20)
      { offer_id: "synthetic-#{ordinal}", record_id: @ids.fetch(ordinal), smiles: fixture.fetch('smiles'),
        extra_data: fixture.fetch('extra_data'), sample: ordinal < 20,
        price_cents: 1000 + ordinal + (refresh && ordinal.zero? ? 25 : 0),
        provenance: { source: 'catalog-native-synthetic-acceptance', fixture_ordinal: ordinal % 20 + 1 } }
    end
    { suppliers: %w[Acme Beta], snapshots: %w[Acme Beta].each_with_index.map do |supplier, parity|
      { supplier: supplier, sequence: sequence, complete: true,
        observed_at: "2026-10-23T01:02:0#{sequence}.123456789Z",
        offers: offers.each_with_index.filter_map { |offer, ordinal| offer if ordinal % 2 == parity } }
    end }
  end

  def import(store, sequence, refresh: false)
    generation = store.stage(manifest(sequence, refresh: refresh))
    selected = refresh ? @ids.first(COUNT - 1) : @ids
    selected.each_slice(200).with_index do |batch, index|
      ack = store.ingest(generation, batch_id: "batch-#{index}", record_ids: batch)
      raise 'acceptance batch acknowledgement differs' unless ack == { 'accepted' => batch.length, 'rejected' => 0 }
      puts JSON.generate(event: 'synthetic_ingest_progress', sequence: sequence, acknowledged: [200 * (index + 1), selected.length].min) if index % 10 == 0
    end
    store.promote(generation)
    generation
  end

  def create
    Dir.mkdir(@directory, 0o700) # Never overwrite a prior acceptance journal.
    store = CatalogGeneration.create(**@options)
    first = import(store, 1)
    queries = @oracle.verify_queries!(first, @ids)
    second = import(store, 2, refresh: true)
    refreshed = store.pointer
    raise 'refresh pointer differs' unless refreshed.values_at('active', 'previous') == [second, first]
    raise 'rollback target differs' unless store.rollback(expected_revision: refreshed.fetch('revision')) == first
    rolled_back = store.verify_active
    raise 'rollback lowered source high-water' unless rolled_back.fetch('high_water') == { 'Acme' => 2, 'Beta' => 2 }
    verify_identity_guards!(store)
    receipt = { pointer: rolled_back, oracle_sha256: Digest::SHA256.file(ENV.fetch('CATALOG_NATIVE_ORACLE')).hexdigest,
                fixture_sha256: Digest::SHA256.file(File.join(__dir__, 'catalog_native_fixture.ndjson')).hexdigest }
    File.open(File.join(@directory, 'receipt.json'), File::WRONLY | File::CREAT | File::EXCL, 0o600) do |file|
      file.write(JSON.generate(receipt)); file.flush; file.fsync
    end
    { native_queries: queries, refresh_offers: COUNT - 1, rollback_verified: true }
  end

  def verify
    receipt = JSON.parse(File.read(File.join(@directory, 'receipt.json')))
    raise 'acceptance oracle changed' unless receipt.fetch('oracle_sha256') == Digest::SHA256.file(ENV.fetch('CATALOG_NATIVE_ORACLE')).hexdigest
    raise 'acceptance fixture changed' unless receipt.fetch('fixture_sha256') == Digest::SHA256.file(File.join(__dir__, 'catalog_native_fixture.ndjson')).hexdigest
    store = CatalogGeneration.new(**@options)
    raise 'retained pointer differs' unless store.verify_active == receipt.fetch('pointer')
    verify_identity_guards!(store)
    { native_queries: @oracle.verify_queries!(store.pointer.fetch('active'), @ids), retained_active_verified: true }
  end

  def verify_restored
    verify
    store = CatalogGeneration.new(**@options)
    before = store.pointer
    target = before.fetch('previous')
    raise 'restored rollback target differs' unless store.rollback(expected_revision: before.fetch('revision')) == target
    after = store.verify_active
    raise 'restored rollback pointer differs' unless after.fetch('active') == target && after.fetch('previous') == before.fetch('active')
    raise 'restored rollback changed high-water' unless after.fetch('high_water') == before.fetch('high_water')
    verify_identity_guards!(store)
    { native_queries: @oracle.verify_queries!(target, @ids), retained_active_verified: true,
      restored_rollback_verified: true, restored_active_offers: COUNT - 1 }
  end

  def verify_identity_guards!(store)
    initial = store.pointer
    stale = manifest(2)
    changed_id = manifest(3)
    changed_id[:snapshots][0][:offers][0][:record_id] = 42
    recycled_id = manifest(3)
    recycled_id[:snapshots][0][:offers][0][:offer_id] = 'replacement-offer'
    [[stale, 'stale source sequence'], [changed_id, 'offer record_id changed'], [recycled_id, 'record_id recycled']].each do |input, reason|
      begin
        store.stage(input)
        raise 'retained identity or sequence guard accepted invalid input'
      rescue CatalogGeneration::Unsafe => error
        raise unless error.message == reason
      end
    end
    raise 'identity guard changed pointer' unless store.pointer == initial
  end
end

Timeout.timeout(600) { CatalogNativeSmoke.new.run }
