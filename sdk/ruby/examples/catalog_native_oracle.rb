# frozen_string_literal: true

require 'delegate'

# Acceptance only. descriptor_audit shares native preparation code with the server,
# so it proves transport/mapping agreement, not independent chemical correctness.
# The first eight structures also have retained Cheminee golden values.
class CatalogNativeOracle < SimpleDelegator
  attr_reader :fixtures, :checked_sources, :fingerprint_field, :goldens

  def initialize(api, oracle_path:)
    super(api)
    @fixtures = read_rows(File.join(__dir__, 'catalog_native_fixture.ndjson'))
    @prepared = read_rows(oracle_path)
    golden_directory = File.expand_path('../../../quickwit/tantivy-rdkit-mapper/tests/fixtures', __dir__)
    raw_goldens = read_rows(File.join(golden_directory, 'descriptor_v1.raw.ndjson'))
    @goldens = read_rows(File.join(golden_directory, 'descriptor_v1.cheminee.ndjson')).map do |row|
      raise 'invalid golden field cardinality' unless row.values.all? { |value| value.is_a?(Array) && value.length == 1 }
      row.transform_values(&:first)
    end
    raise 'unexpected acceptance fixture size' unless @fixtures.length == 20 && @prepared.length == 20 && @goldens.length == 8
    raise 'golden input differs' unless @fixtures.first(8) == raw_goldens
    @prepared.zip(@fixtures).each do |prepared, input|
      raise 'oracle order or metadata differs' unless prepared.fetch('extra_data') == input.fetch('extra_data')
      raise 'oracle descriptor membership differs' unless prepared.fetch('descriptors').keys.sort == CatalogGeneration::NativePreparation::DESCRIPTORS.sort
    end
    @fingerprint_field = CatalogGeneration::NativePreparation.new(
      spec: CatalogGeneration::NativePreparation::SPEC, prepared_smiles_field: 'prepared_smiles'
    ).fingerprint_field
    @prepared.first(8).zip(@goldens).each { |prepared, golden| verify_golden!(prepared, golden) }
    @checked_sources = 0
  end

  def search_composable_unchecked_with_http_info(index, body, **options)
    result = __getobj__.search_composable_unchecked_with_http_info(index, body, **options)
    response, status = result
    if status == 200 && response.is_a?(Hash) && response.dig(:hits, :hits).is_a?(Array)
      response[:hits][:hits].each do |hit|
        source = JSON.parse(JSON.generate(hit.fetch(:_source)))
        fixture_id = source.fetch('extra_data').fetch('record_id')
        raise 'unexpected fixture identity' unless fixture_id.is_a?(Integer) && (1..20).cover?(fixture_id)
        verify_source!(source, @prepared.fetch(fixture_id - 1))
        @checked_sources += 1
      end
    end
    result
  end

  def verify_queries!(generation, record_ids)
    spec = QuickwitCheminee::FingerprintSpec.new(CatalogGeneration::NativePreparation::SPEC)
    request = QuickwitCheminee::GraphSearchRequest.new(
      spec: spec, smiles: 'CC', result_limit: 100, use_chirality: false,
      include_identity: true, ranking: 'stable_id', prepared_smiles_field: 'prepared_smiles',
      extra_query: sample_filter(9..14)
    )
    identity = __getobj__.cheminee_v1_identity(generation, request)
    check_hits!(identity, [[record_ids.fetch(8), 1.0]])
    substructure = __getobj__.cheminee_v1_substructure(generation, request)
    check_hits!(substructure, [8, 9, 10, 13].map { |ordinal| [record_ids.fetch(ordinal), 1.0] })
    query_bytes = Base64.strict_decode64(@goldens.first.fetch('morgan_fingerprint')).bytes
    expected = @goldens.each_with_index.filter_map do |golden, ordinal|
      candidate = Base64.strict_decode64(golden.fetch('morgan_fingerprint')).bytes
      intersection = query_bytes.zip(candidate).sum { |left, right| popcount(left & right) }
      union = query_bytes.zip(candidate).sum { |left, right| popcount(left | right) }
      score = intersection.to_f / union
      [record_ids.fetch(ordinal), score] if score >= 0.2
    end.sort_by { |id, score| [-score, id] }
    similarity = __getobj__.cheminee_v1_similarity(generation, QuickwitCheminee::SmilesSimilarityRequest.new(
      spec: spec, smiles: 'CCO', tanimoto_minimum: 0.2, result_limit: 100,
      extra_query: sample_filter(1..8)
    ))
    check_hits!(similarity, expected)
    { identity_matches: 1, substructure_matches: 4, golden_similarity_matches: expected.length }
  end

  private

  def read_rows(path)
    File.foreach(path).map { |line| JSON.parse(line) }
  end

  def popcount(byte)
    byte.digits(2).sum
  end

  def sample_filter(ordinals)
    # Dynamic metadata supports terms; do not require a non-fast JSON range.
    'sample:true AND (' + ordinals.map { |ordinal| "extra_data.record_id:#{ordinal}" }.join(' OR ') + ')'
  end

  def check_hits!(response, expected)
    raise 'native facade total differs' unless response.num_hits == expected.length && response.hits.length == expected.length
    response.hits.zip(expected).each do |hit, (id, score)|
      raise 'native facade membership or ordering differs' unless hit.record_id == id.to_s
      raise 'native facade score differs' unless hit.score.is_a?(Numeric) && hit.score.finite? && (hit.score - score).abs <= 1e-6
    end
  end

  def same_number?(actual, expected)
    return actual == expected if expected.is_a?(Integer)
    return false unless actual.is_a?(Numeric) && actual.finite? && expected.is_a?(Float) && expected.finite?
    # Existing descriptor REST acceptance permits one ULP of JSON float round trip.
    tolerance = [expected.next_float - expected, expected - expected.prev_float].max
    (actual - expected).abs <= tolerance
  end

  def verify_golden!(prepared, golden)
    %w[smiles morgan_fingerprint pattern_fingerprint other_descriptors extra_data].each do |field|
      raise 'CLI preparation differs from Cheminee golden' unless prepared.fetch(field) == golden.fetch(field)
    end
    prepared.fetch('descriptors').each do |name, value|
      raise 'CLI descriptor differs from Cheminee golden' unless same_number?(value, golden.fetch(name))
    end
  end

  def verify_source!(source, prepared)
    raise 'stored prepared SMILES differs from CLI oracle' unless source.fetch('prepared_smiles') == prepared.fetch('smiles')
    expected_hex = Base64.strict_decode64(prepared.fetch('morgan_fingerprint')).unpack1('H*')
    raise 'stored Morgan fingerprint differs from CLI oracle' unless source.fetch(@fingerprint_field) == expected_hex
    %w[pattern_fingerprint other_descriptors].each do |field|
      raise 'stored derived fields differ from CLI oracle' unless source.fetch(field) == prepared.fetch(field)
    end
    actual_descriptors = source.fetch('descriptors')
    raise 'stored descriptor membership differs' unless actual_descriptors.keys.sort == CatalogGeneration::NativePreparation::DESCRIPTORS.sort
    prepared.fetch('descriptors').each do |name, value|
      expected = if name.start_with?('Num', 'lipinski')
                   raise 'nonintegral oracle count descriptor' unless value == value.to_i
                   value.to_i
                 else
                   value
                 end
      raise 'stored descriptor differs from CLI oracle' unless same_number?(actual_descriptors.fetch(name), expected)
    end
  end
end
