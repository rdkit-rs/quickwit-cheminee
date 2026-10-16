# frozen_string_literal: true

# Run only against a disposable local server. This creates and deletes its own index.
# This smoke deliberately uses a non-native server; chemistry requests must reject
# absent native capability rather than returning empty successful results.
require 'quickwit-cheminee'
require 'json'
require 'securerandom'

config = QuickwitCheminee::Configuration.new
config.scheme = 'http'
config.host = ENV.fetch('SDK_SMOKE_HOST')
config.base_path = ''
config.timeout = 60 # Smoke deadline, not a production tuning recommendation.
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
index_id = "ruby-sdk-smoke-#{SecureRandom.hex(4)}"
created = false
raise 'Node is not ready' unless api.ready

begin
  created = true # Clean up even if response decoding fails after a successful create.
  metadata = api.create_index({
    version: '0.9', index_id: index_id,
    doc_mapping: {mode: 'dynamic', dynamic_mapping: {fast: false, stored: true}, field_mappings: [
      {name: 'record_id', type: 'u64', fast: true, stored: true},
      {name: 'smiles', type: 'text', stored: true},
      {name: 'metadata', type: 'json', stored: true}
    ]}, indexing_settings: {commit_timeout_secs: 1}
  })
  raise 'Create response lost index config' unless metadata.index_config.index_id == index_id
  mapping = metadata.index_config.doc_mapping
  id_mapping = mapping.field_mappings.find { |field| field.name == 'record_id' }.to_hash
  raise 'Numeric mapping options lost' unless id_mapping[:fast] == true && id_mapping[:stored] == true
  raise 'Dynamic fast false lost' unless mapping.dynamic_mapping.fast == false
  rows = [
    {record_id: 1, smiles: 'CCO', metadata: {supplier: 'Acme', available: true, note: '東京'}},
    {record_id: 2, smiles: 'CCN', metadata: {supplier: 'Elsewhere', available: false}},
    {record_id: 'invalid-u64', smiles: 'CCC', metadata: {supplier: 'Rejected'}}
  ]
  response = api.ingest(index_id, rows.map { |row| JSON.generate(row) }.join("\n") + "\n",
                        commit: 'force', detailed_response: true)
  raise 'Acceptance/rejection counts incorrect' unless response.num_ingested_docs == 2 && response.num_rejected_docs == 1
  raise 'Rejected document detail missing' unless response.parse_failures&.length == 1
  result = api.cheminee_v1_basic(index_id, {query: 'metadata.supplier:Acme', result_limit: 10})
  raise 'Filtered search mismatch' unless result.num_hits == 1 && result.hits.length == 1
  raise 'Nested metadata lost' unless result.hits.first.dig(:metadata, :note) == '東京'
  raise 'Published count mismatch' unless api.describe_index(index_id).num_published_docs == 2
  spec = {format: 'morgan-r3-2048-lsb0-v1', preparation_id: 'sanitize-only-v1', rdkit_version: '2026.09.1'}
  %w[identity substructure superstructure similarity].each do |kind|
    begin
      api.public_send("cheminee_v1_#{kind}", index_id, {smiles: 'CCO', spec: spec})
      raise "#{kind} silently accepted unavailable chemistry capability"
    rescue QuickwitCheminee::ApiError => error
      raise unless error.code == 400 && error.response_body.include?('native-chemistry')
    end
  end
  puts JSON.generate({status: 'passed', scope: 'live non-native PR3 importer contract',
                      accepted: 2, rejected: 1, filtered_hits: 1, unavailable_chemistry_errors: 4})
ensure
  api.delete_index(index_id) if created
end
