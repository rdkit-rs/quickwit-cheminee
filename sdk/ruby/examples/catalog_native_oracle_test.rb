# frozen_string_literal: true
# Acceptance-checker tests with a fake wire peer; no native preparation/HTTP claim.
require 'minitest/autorun'
require 'tmpdir'
require_relative 'catalog_generation'
require_relative 'catalog_native_oracle'
require_relative 'catalog_test_peer'

class CatalogNativeOracleTest < Minitest::Test
  def setup
    @temporary = Dir.mktmpdir('catalog-oracle-check-')
    @path = File.join(@temporary, 'oracle.ndjson')
    fixtures = File.foreach(File.join(__dir__, 'catalog_native_fixture.ndjson')).map { |line| JSON.parse(line) }
    golden_path = File.expand_path('../../../quickwit/tantivy-rdkit-mapper/tests/fixtures/descriptor_v1.cheminee.ndjson', __dir__)
    goldens = File.foreach(golden_path).map { |line| JSON.parse(line).transform_values(&:first) }
    @prepared = fixtures.each_with_index.map do |input, ordinal|
      # Only the first eight have golden chemistry; remaining rows are test filler.
      golden = goldens.fetch(ordinal % goldens.length)
      fields = golden.reject { |name, _| CatalogGeneration::NativePreparation::DESCRIPTORS.include?(name) }
      fields.merge('extra_data' => input.fetch('extra_data'),
        'descriptors' => CatalogGeneration::NativePreparation::DESCRIPTORS.to_h { |name| [name, golden.fetch(name).to_f] })
    end
    @peer = CatalogTestPeer.new
    persist_oracle
  end

  def teardown
    FileUtils.remove_entry(@temporary)
  end

  def persist_oracle
    File.write(@path, @prepared.map { |row| JSON.generate(row) }.join("\n") + "\n")
  end

  def oracle
    CatalogNativeOracle.new(@peer, oracle_path: @path)
  end

  def test_cli_shape_and_golden_prefix_are_validated_without_claiming_test_filler_truth
    checker = oracle
    assert_equal 8, checker.goldens.length
    assert_equal 20, checker.fixtures.length
    @prepared.first['smiles'] = 'changed'
    persist_oracle
    assert_raises(RuntimeError) { oracle }
  end

  def test_oracle_metadata_order_and_descriptor_membership_fail_closed
    @prepared.last['extra_data']['record_id'] = 19
    persist_oracle
    assert_raises(RuntimeError) { oracle }
    @prepared.last['extra_data']['record_id'] = 20
    @prepared.last['descriptors'].delete('amw')
    persist_oracle
    assert_raises(RuntimeError) { oracle }
  end

  def test_wire_source_oracle_rejects_altered_derived_values_and_counts_valid_sources
    checker = oracle
    expected = @prepared.first
    source = { 'record_id' => (1 << 64) - 1, 'extra_data' => expected.fetch('extra_data'),
               'prepared_smiles' => expected.fetch('smiles'),
               checker.fingerprint_field => Base64.strict_decode64(expected.fetch('morgan_fingerprint')).unpack1('H*'),
               'pattern_fingerprint' => expected.fetch('pattern_fingerprint'),
               'other_descriptors' => expected.fetch('other_descriptors'),
               'descriptors' => expected.fetch('descriptors').to_h { |name, value| [name, name.start_with?('Num', 'lipinski') ? value.to_i : value] } }
    index = 'offers-012345678901234567890123'
    @peer.rows[index] = [source]
    body = { query: { match_all: {} }, from: 0, size: 1, sort: [{ record_id: 'asc' }] }
    checker.search_composable_unchecked_with_http_info(index, body, allow_partial_search_results: false)
    assert_equal 1, checker.checked_sources
    source['descriptors']['amw'] = source['descriptors']['amw'].next_float
    checker.search_composable_unchecked_with_http_info(index, body, allow_partial_search_results: false)
    assert_equal 2, checker.checked_sources
    source['descriptors']['amw'] = source['descriptors']['amw'].next_float
    assert_raises(RuntimeError) { checker.search_composable_unchecked_with_http_info(index, body, allow_partial_search_results: false) }
  end
end
