# frozen_string_literal: true
# Synthetic derived values exercise audit policy only, never native chemistry truth.
require 'minitest/autorun'
require 'tmpdir'
require_relative 'catalog_generation'
require_relative 'catalog_test_peer'

class CatalogNativePreparationTest < Minitest::Test
  include CatalogTestJournal

  def native_config
    { spec: CatalogGeneration::NativePreparation::SPEC, prepared_smiles_field: 'prepared_smiles' }
  end

  def profile_options
    { native_preparation: native_config, index_heap_size_bytes: 32 * 1024 * 1024 }
  end

  def test_mapper_contract_preserves_raw_offers_and_keeps_derived_values_out_of_ingest
    generation = ready([0, (1 << 64) - 1])
    mapping = @api.mappings.fetch(generation).fetch('doc_mapping')
    assert_equal true, mapping['chemistry']['descriptor_v1']
    assert_equal 'nested', mapping['chemistry']['descriptor_layout']
    assert_equal 'smiles', mapping['chemistry']['smiles_field']
    assert_equal 'prepared_smiles', mapping['chemistry']['prepared_smiles_field']
    prepared = mapping['field_mappings'].find { |field| field['name'] == 'prepared_smiles' }
    assert_equal [true, true, false], prepared.values_at('stored', 'fast', 'indexed')
    fingerprint = mapping['field_mappings'].find { |field| field['name'].start_with?('morgan_') }
    assert_equal 'morgan_5be8b9ad4f8bbdce84f376944d49b996d976e6676f07fd6ee416c0357903141e', fingerprint['name']
    assert_equal %w[hex hex], fingerprint.values_at('input_format', 'output_format')
    assert_equal state(generation)['records'], @api.ingest_bodies.first.lines.map { |line| JSON.parse(line) }
    assert_equal '33554432 B', @api.mappings[generation]['indexing_settings']['resources']['heap_size']
    assert_equal generation, @store.promote(generation)
    assert_equal generation, reopen(**profile_options).verify_active['active']
  end

  def test_native_configuration_is_explicit_and_pinned_for_scope_and_generations
    generation = ready([1])
    @store.promote(generation)
    assert_raises(CatalogGeneration::Unsafe) { reopen }
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: native_config) }
    assert_raises(CatalogGeneration::Unsafe) { reopen(**profile_options.merge(index_heap_size_bytes: 64 * 1024 * 1024)) }
    assert_raises(CatalogGeneration::Unsafe) { reopen(**profile_options.merge(index_heap_size_bytes: -1)) }
    changed = native_config.merge(prepared_smiles_field: 'canonical_smiles')
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: changed) }
    bad_spec = native_config.merge(spec: native_config[:spec].merge('rdkit_version' => 'other'))
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: bad_spec) }
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: {}) }
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: native_config.merge(descriptor_v1: false)) }
    path = File.join(@directory, "#{generation}.json")
    modified = state(generation).merge('profile' => CatalogGeneration::LEGACY_PROFILE)
    File.write(path, JSON.generate(modified))
    assert_raises(CatalogGeneration::Unsafe) { reopen(**profile_options) }
  end

  def test_caller_cannot_supply_known_derived_fields
    names = %w[prepared_smiles descriptors other_descriptors pattern_fingerprint NumAtoms]
    names << CatalogGeneration::NativePreparation.new(native_config).fingerprint_field
    names.each do |name|
      input = manifest([1])
      input[:snapshots][0][:offers][0][name] = nil
      assert_raises(CatalogGeneration::Unsafe) { @store.stage(input) }
    end
    assert_empty @api.mappings
  end

  def test_every_derived_field_is_required_and_extra_original_fields_are_rejected
    generation = ready([1])
    original = @api.rows[generation][0]
    fields = original.keys - state(generation)['records'][0].keys
    fields.each_with_index do |name, index|
      candidate = ready([1], sequence: index + 2)
      @api.rows[candidate][0].delete(name)
      rejected_promotion(candidate)
    end
    @api.rows[generation][0]['extra'] = 'not in original offer'
    rejected_promotion(generation)
  end

  def test_bad_derived_shape_is_never_ignored
    mutations = [
      ->(row) { row['prepared_smiles'] = ['CCO'] },
      ->(row) { row[row.keys.find { |name| name.start_with?('morgan_') }] = '0' * 512 },
      ->(row) { row['pattern_fingerprint'] = Base64.strict_encode64('short') },
      ->(row) { row['descriptors']['NumAtoms'] = 1.0 },
      ->(row) { row['descriptors']['amw'] = 1 },
      ->(row) { row['descriptors'].delete('amw') },
      ->(row) { row['descriptors']['unknown'] = 1.0 },
      ->(row) { row['other_descriptors']['scaffolds'] = 'not an array' },
      ->(row) { row['other_descriptors']['scaffolds'] = [1 << 63] },
      ->(row) { row['other_descriptors']['similarity_cluster'] = 10_000 },
      ->(row) { row['other_descriptors']['unexpected'] = true }
    ]
    mutations.each_with_index do |mutation, index|
      generation = ready([1], sequence: index + 1)
      mutation.call(@api.rows[generation][0])
      rejected_promotion(generation)
    end
  end

  def test_full_refresh_withdrawal_rollback_and_original_source_integrity
    first = ready([1, 2], sequence: 1)
    @store.promote(first)
    second = ready([1], sequence: 2, price: 12)
    @store.promote(second)
    current = @store.pointer
    assert_equal first, @store.rollback(expected_revision: current['revision'])
    assert_equal current['high_water'], @store.pointer['high_water']
    assert_raises(CatalogGeneration::Unsafe) { @store.stage(manifest([1, 2], sequence: 2)) }
    assert_equal first, @store.verify_active['active']
    @api.rows[second][0]['smiles'] = 'CCO'
    before = @store.pointer
    assert_raises(CatalogGeneration::Unsafe) { @store.rollback(expected_revision: before['revision']) }
    assert_equal before, @store.pointer
  end

  def test_native_audit_checks_original_provenance_and_identity
    %w[offer_id supplier observed_at provenance].each_with_index do |field, index|
      generation = ready([1], sequence: index + 1)
      @api.rows[generation][0][field] = 'changed'
      rejected_promotion(generation)
    end
  end
end

class CatalogLegacyProfileTest < Minitest::Test
  include CatalogTestJournal

  def test_preexisting_legacy_journal_opens_without_migrating_or_enabling_native_mode
    generation = ready([1])
    @store.promote(generation)
    ['scope.json', "#{generation}.json"].each do |name|
      path = File.join(@directory, name)
      document = JSON.parse(File.read(path))
      document.delete('profile')
      File.write(path, JSON.generate(document))
    end
    assert_equal generation, reopen.verify_active['active']
    native = { spec: CatalogGeneration::NativePreparation::SPEC, prepared_smiles_field: 'prepared_smiles' }
    assert_raises(CatalogGeneration::Unsafe) { reopen(native_preparation: native) }
    assert_nil @api.mappings[generation]['doc_mapping']['chemistry']
    assert_equal %w[suppliers], JSON.parse(File.read(File.join(@directory, 'scope.json'))).keys
  end
end
