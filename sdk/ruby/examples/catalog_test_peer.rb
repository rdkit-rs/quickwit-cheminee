# frozen_string_literal: true

# In-memory wire-shaped test peer, not a chemistry implementation or runtime proof.
class CatalogTestPeer
  attr_accessor :mutate_response
  attr_reader :rows, :requests, :mappings, :ingest_bodies

  def initialize
    @rows, @requests, @mappings, @ingest_bodies = {}, [], {}, []
  end

  def create_index(mapping, **)
    name = mapping.fetch(:index_id)
    @mappings[name] = JSON.parse(JSON.generate(mapping))
    @rows[name] = []
  end

  def ingest(index, body, **)
    @ingest_bodies << body
    records = body.lines.map { |line| JSON.parse(line) }
    chemistry = @mappings.fetch(index).fetch('doc_mapping')['chemistry']
    @rows.fetch(index).concat(records.map { |record| chemistry ? record.merge(derived(chemistry)) : record })
    Struct.new(:num_ingested_docs, :num_rejected_docs).new(records.length, 0)
  end

  def search_composable_unchecked_with_http_info(index, body, **options)
    raise 'partial search must be disabled' unless options[:allow_partial_search_results] == false
    @requests << body
    selected = @rows.fetch(index).sort_by { |record| record.fetch('record_id') }
    if body[:query][:range]
      bounds = body[:query].fetch(:range).fetch(:record_id)
      selected = selected.select { |record| (bounds.fetch(:gte)..bounds.fetch(:lte)).cover?(record.fetch('record_id')) }
    elsif body[:query] != { match_all: {} }
      raise 'unsupported test query'
    end
    hits = selected.drop(body.fetch(:from)).first(body.fetch(:size)).map do |record|
      source = JSON.parse(JSON.generate(record), symbolize_names: true)
      id = record.fetch('record_id')
      { _index: index, _source: source, sort: body[:sort] == [{ record_id: 'asc' }] ? [id] : [1.0, id] }
    end
    response = { timed_out: false, _shards: { total: 1, successful: 1, failed: 0, skipped: 0 },
                 hits: { total: { value: selected.length, relation: 'eq' }, hits: hits } }
    @mutate_response&.call(response, body)
    [response, 200, {}]
  end

  def derived(chemistry)
    fingerprint = 'morgan_' + Digest::SHA256.hexdigest("morgan-r3-2048-lsb0-chiral0-features0-v1\0#{chemistry['spec']['rdkit_version']}\0#{chemistry['spec']['preparation_id']}")
    { chemistry.fetch('prepared_smiles_field') => 'CCO', fingerprint => '01' + '00' * 255,
      'pattern_fingerprint' => Base64.strict_encode64("\x01" * 256),
      'descriptors' => CatalogGeneration::NativePreparation::DESCRIPTORS.to_h { |name| [name, name.start_with?('Num', 'lipinski') ? 1 : 1.0] },
      'other_descriptors' => { 'scaffolds' => [-1], 'similarity_cluster' => 3 } }
  end
end

module CatalogTestJournal
  def setup
    @temporary = Dir.mktmpdir('catalog-bounded-')
    @directory = File.join(@temporary, 'journal')
    @api = CatalogTestPeer.new
    @store = CatalogGeneration.create(api: @api, directory: @directory, expected_suppliers: ['Acme'], **profile_options)
  end

  def teardown
    FileUtils.remove_entry(@temporary)
  end

  def profile_options
    {}
  end

  def manifest(ids, sequence: 1, price: 10)
    { suppliers: ['Acme'], snapshots: [{ supplier: 'Acme', complete: true, sequence: sequence,
      observed_at: '2026-10-23T01:02:03.123456789Z', offers: ids.map do |id|
        { offer_id: "offer-#{id}", record_id: id, smiles: 'OCC', price: price,
          provenance: { source: 'synthetic', tags: ['one', 'two'] } }
      end }] }
  end

  def ready(ids, sequence: 1, price: 10)
    generation = @store.stage(manifest(ids, sequence: sequence, price: price))
    @store.ingest(generation, batch_id: 'batch', record_ids: ids)
    generation
  end

  def state(generation)
    JSON.parse(File.read(File.join(@directory, "#{generation}.json")))
  end

  def reopen(**options)
    CatalogGeneration.new(api: @api, directory: @directory, expected_suppliers: ['Acme'], **options)
  end

  def rejected_promotion(generation)
    before = @store.pointer
    assert_raises(CatalogGeneration::Unsafe) { @store.promote(generation) }
    assert_equal before, @store.pointer
    assert_equal 'quarantined', state(generation).fetch('status')
  end
end
