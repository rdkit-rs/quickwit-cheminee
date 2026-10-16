# frozen_string_literal: true

require 'minitest/autorun'
require 'socket'
require 'timeout'
require 'json'
require 'stringio'
require 'quickwit-cheminee'
require 'bundler'

# Verify the actual activated transport/test dependencies, including transitives.
lock = Bundler::LockfileParser.new(Bundler.read_file(File.join(__dir__, 'Gemfile.lock')))
lock.specs.each do |locked|
  loaded = Gem.loaded_specs[locked.name]
  raise "Dependency differs from lock: #{locked.name}" unless loaded && loaded.version == locked.version
end

# These are real HTTP transport tests against a controlled fixture peer. They
# establish installed-gem wire behavior, not chemistry truth or storage durability.
class InstalledGemWireTest < Minitest::Test
  def exchange(response, status: 200, timeout: nil, delay: 0)
    listener = TCPServer.new('127.0.0.1', 0)
    captured = nil
    thread = Thread.new do
      socket = listener.accept
      line = socket.gets("\r\n")
      headers = {}
      while (header = socket.gets("\r\n")) != "\r\n"
        key, value = header.split(':', 2)
        headers[key.downcase] = value.strip
      end
      body = socket.read(Integer(headers.fetch('content-length', '0')))
      captured = { line: line, headers: headers, body: body }
      sleep(delay)
      payload = JSON.generate(response)
      socket.write("HTTP/1.1 #{status} Fixture\r\nContent-Type: application/json\r\n" \
                   "Content-Length: #{payload.bytesize}\r\nX-Request-Id: fixture-42\r\n" \
                   "Connection: close\r\n\r\n#{payload}")
    rescue Errno::EPIPE, Errno::ECONNRESET
      raise unless delay.positive?
    ensure
      socket&.close
    end
    config = QuickwitCheminee::Configuration.new
    config.scheme = 'http'
    config.host = "127.0.0.1:#{listener.addr[1]}"
    config.base_path = ''
    config.timeout = timeout if timeout
    output = StringIO.new
    config.logger = Logger.new(output)
    api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
    result = yield api
    Timeout.timeout(5) { thread.value }
    assert_nil IO.select([listener], nil, nil, 0), 'unexpected implicit retry connection'
    assert_empty output.string, 'routine requests must not log catalog contents'
    [result, captured]
  ensure
    thread&.kill if thread&.alive?
    listener&.close
  end

  def test_loaded_from_installed_gem
    spec = Gem.loaded_specs.fetch('quickwit-cheminee')
    assert spec.full_gem_path.start_with?(ENV.fetch('SDK_INSTALL_ROOT'))
    assert_equal ENV.fetch('SDK_EXPECTED_VERSION', '0.9.1.pre.pr3'), QuickwitCheminee::VERSION
  end

  def test_unicode_ndjson_mixed_rejections_and_http_metadata
    body = [{smiles: 'CCO', metadata: {supplier: 'München', offer: 'α'}},
            {smiles: 'invalid', metadata: {supplier: '東京'}}].map { |d| JSON.generate(d) }.join("\n") + "\n"
    response = {num_docs_for_processing: 2, num_ingested_docs: 1, num_rejected_docs: 1,
                parse_failures: [{reason: 'invalid_schema', message: 'invalid SMILES', document: 'invalid'}]}
    result, request = exchange(response) do |api|
      api.ingest_with_http_info('offers', body, commit: 'wait_for', detailed_response: true)
    end
    model, status, headers = result
    assert_equal body.b, request[:body].b
    assert_equal body.bytesize.to_s, request[:headers]['content-length']
    assert_equal 'application/x-ndjson', request[:headers]['content-type']
    assert_includes request[:line], 'commit=wait_for'
    assert_includes request[:line], 'detailed_response=true'
    assert_equal 200, status
    assert_equal 'fixture-42', headers['x-request-id']
    assert_equal 1, model.num_ingested_docs
    assert_equal 1, model.num_rejected_docs
    assert_equal 'invalid_schema', model.parse_failures.first.reason
    assert_equal 'invalid', model.parse_failures.first.document
  end

  def test_unknown_acceptance_is_nil_and_false_option_survives
    model, request = exchange({num_docs_for_processing: 1}) do |api|
      api.ingest('offers', "{\"smiles\":\"CCO\"}\n", detailed_response: false)
    end
    assert_nil model.num_ingested_docs
    assert_nil model.num_rejected_docs
    assert_nil model.parse_failures
    assert_includes request[:line], 'detailed_response=false'
  end

  def test_create_index_round_trips_versioned_metadata_and_chemistry
    spec = {format: 'morgan-r3-2048-lsb0-v1', preparation_id: 'sanitize-only-v1', rdkit_version: '2026.09.1'}
    config = {version: '0.9', index_id: 'offers', doc_mapping: {
      mode: 'dynamic', field_mappings: [
        {name: 'record_id', type: 'u64', fast: true, stored: false},
        {name: 'offers', type: 'object', field_mappings: [
          {name: 'supplier', type: 'text', tokenizer: 'raw', fast: {normalizer: 'lowercase'}}]}],
      dynamic_mapping: {fast: false, stored: true}, chemistry: {spec: spec, smiles_field: 'smiles', prepared_smiles_field: 'prepared_smiles'}}}
    response = {version: '0.9', index_uid: 'offers:00000000000000000000000000',
                index_config: config, checkpoint: {}, sources: [], create_timestamp: 123}
    model, request = exchange(response) { |api| api.create_index(config) }
    assert_equal config, JSON.parse(request[:body], symbolize_names: true)
    refute_nil model
    assert_equal 'offers', model.index_config.index_id
    assert_equal '0.9', model.index_config.version
    assert_equal spec[:preparation_id], model.index_config.doc_mapping.chemistry.spec.preparation_id
    assert_equal config[:doc_mapping], model.index_config.doc_mapping.to_hash
  end

  def test_mapping_options_and_fast_field_wire_variants
    [false, true, {normalizer: 'raw'}, {normalizer: 'lowercase'}].each do |value|
      actual = QuickwitCheminee::FastFieldOptions.build(value)
      assert_equal value, actual.respond_to?(:to_hash) ? actual.to_hash : actual
    end
    options = {name: 'custom', type: 'text', stored: false, nullable_option: nil,
               extensions: [nil, false, 7, {label: '東京'}]}
    built = QuickwitCheminee::FieldMappingEntryForSerialization.build_from_hash(options)
    assert_equal options, built.to_hash
    assert_equal options, QuickwitCheminee::FieldMappingEntryForSerialization.new(options).to_hash
    assert_equal false, built.additional_properties[:stored]
    refute_equal built, QuickwitCheminee::FieldMappingEntryForSerialization.new(name: 'custom', type: 'text')
  end

  def test_delete_deserializes_actual_split_info
    response = [{split_id: 'split-1', num_docs: 2, uncompressed_docs_size_bytes: 71,
                 file_name: 'split-1.split', file_size_bytes: 121}]
    model, request = exchange(response) { |api| api.delete_index('offers', dry_run: true) }
    assert_kind_of QuickwitCheminee::SplitInfo, model.first
    assert_equal 2, model.first.num_docs
    assert_includes request[:line], 'dry_run=true'
  end

  def test_versioned_sources_and_tokenizers_preserve_nested_fields
    examples = {
      'file' => {filepath: '/catalog/input.ndjson', notifications: []},
      'ingest' => nil, 'ingest-api' => nil, 'ingest-cli' => nil,
      'kafka' => {topic: 'offers', client_params: {'bootstrap.servers' => 'broker:9092'}, enable_backfill_mode: false},
      'kinesis' => {stream_name: 'offers', enable_backfill_mode: false},
      'pubsub' => {subscription: 'offers', project_id: 'test-project'},
      'pulsar' => {address: 'pulsar://broker:6650', topics: ['offers'], consumer_name: 'quickwit'},
      'stdin' => nil, 'vec' => {docs: ['{}'], batch_num_docs: 1, partition: 'test'},
      'void' => nil
    }
    %w[0.7 0.9].each do |version|
      examples.each do |kind, params|
        source = {version: version, source_id: 'supplier', source_type: kind, enabled: false, input_format: 'json'}
        source.merge!(version == '0.7' ? {desired_num_pipelines: 1, max_num_pipelines_per_indexer: 1} : {num_pipelines: 1})
        source[:params] = params if params || kind == 'void'
        built = QuickwitCheminee::VersionedSourceConfig.build(source)
        refute_nil built, kind
        assert_equal source, built.to_hash, "#{version}/#{kind} loses fields"
      end
    end
    [{name: 'ngrams', type: 'ngram', min_gram: 2, max_gram: 4, prefix_only: false},
     {name: 'regexes', type: 'regex', pattern: '[a-z]+'},
     {name: 'words', type: 'simple'}, {name: 'code', type: 'source_code'}].each do |tokenizer|
      tokenizer[:filters] = ['lower_caser']
      assert_equal tokenizer, QuickwitCheminee::TokenizerEntry.build(tokenizer).to_hash
    end
  end

  def test_unknown_or_missing_discriminators_raise_instead_of_dropping_sources
    [{source_type: 'ingest'}, {version: '999', source_type: 'ingest'},
     {version: '0.9'}, {version: '0.9', source_type: 'new-unknown-source'}].each do |value|
      assert_raises(QuickwitCheminee::ApiError) { QuickwitCheminee::VersionedSourceConfig.build(value) }
    end
  end

  def test_five_search_methods_preserve_payloads_and_large_ids
    spec = {format: 'morgan-r3-2048-lsb0-v1', preparation_id: 'sanitize-only-v1', rdkit_version: '2026.09.1'}
    document = {record_id: 18_446_744_073_709_551_615, smiles: 'CCO',
                metadata: {supplier: '東京', offers: [{price: 1.25, available: false}]}}
    %w[basic identity substructure superstructure similarity].each do |kind|
      request_body = kind == 'basic' ? {query: '*', result_limit: 1} :
        {spec: spec, smiles: 'CCO', result_limit: 1}
      hit = kind == 'basic' ? document : {record_id: document[:record_id].to_s, score: 1.0, document: document}
      response = {num_hits: 1, hits: [hit], searched_splits: 1, elapsed_time_micros: 10}
      model, captured = exchange(response) { |api| api.public_send("cheminee_v1_#{kind}", 'offers', request_body) }
      assert_includes captured[:line], "POST /v1/indexes/offers/search/#{kind} "
      assert_equal request_body, JSON.parse(captured[:body], symbolize_names: true)
      actual = kind == 'basic' ? model.hits.first : model.hits.first.document
      assert_equal document, actual
    end
  end

  def test_incomplete_search_error_preserves_status_and_request_id
    response = {message: 'incomplete chemistry search'}
    error, = exchange(response, status: 503) do |api|
      assert_raises(QuickwitCheminee::ApiError) { api.cheminee_v1_basic('offers', {query: '*'}) }
    end
    assert_equal 503, error.code
    assert_equal response, JSON.parse(error.response_body, symbolize_names: true)
    assert_equal 'fixture-42', error.response_headers['x-request-id']
  end

  def test_write_timeout_is_an_error_without_automatic_retry
    error, captured = exchange({num_docs_for_processing: 1}, timeout: 0.05, delay: 0.2) do |api|
      assert_raises(QuickwitCheminee::ApiError) { api.ingest('offers', "{}\n") }
    end
    assert_includes error.message, 'timed out'
    assert_equal "{}\n", captured[:body]
  end

  def test_legacy_namespace_can_coexist
    $LOAD_PATH.unshift(ENV.fetch('LEGACY_CHEMINEE_LIB'))
    require 'cheminee'
    legacy = Cheminee::Configuration.default
    original_host = legacy.host
    modern = QuickwitCheminee::Configuration.new
    modern.host = 'example.invalid'
    assert_equal original_host, legacy.host
    refute_same Cheminee::ApiClient, QuickwitCheminee::ApiClient
  end
end
