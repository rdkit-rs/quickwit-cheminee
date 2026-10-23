# frozen_string_literal: true

require 'base64'

class CatalogGeneration
  # This opt-in profile follows quickwit-doc-mapper/src/chemistry.rs: nested
  # descriptor_v1, raw input SMILES retained separately from prepared SMILES.
  # Output shape is audited here; chemical correctness requires an external oracle.
  class NativePreparation
    SPEC = {
      'format' => 'morgan-r3-2048-lsb0-v1', 'rdkit_version' => '2026.09.1',
      'preparation_id' => 'cheminee-fragment-tautomer-neutralize-v1'
    }.freeze
    DESCRIPTORS = %w[
      CrippenClogP CrippenMR FractionCSP3 NumAliphaticHeterocycles NumAliphaticRings
      NumAmideBonds NumAromaticHeterocycles NumAromaticRings NumAtomStereoCenters
      NumAtoms NumBridgeheadAtoms NumHBA NumHBD NumHeavyAtoms NumHeteroatoms
      NumHeterocycles NumRings NumRotatableBonds NumSaturatedHeterocycles
      NumSaturatedRings NumSpiroAtoms NumUnspecifiedAtomStereoCenters Phi amw
      chi0n chi0v chi1n chi1v chi2n chi2v chi3n chi3v chi4n chi4v exactmw
      hallKierAlpha kappa1 kappa2 kappa3 labuteASA lipinskiHBA lipinskiHBD tpsa
    ].freeze

    attr_reader :profile, :fingerprint_field

    def initialize(configuration)
      config = JSON.parse(JSON.generate(configuration))
      raise Unsafe, 'invalid native preparation configuration' unless config.is_a?(Hash) && config.keys.sort == %w[prepared_smiles_field spec]
      raise Unsafe, 'unsupported native preparation specification' unless config.fetch('spec') == SPEC
      @prepared_field = config.fetch('prepared_smiles_field')
      unless @prepared_field.is_a?(String) && /\A[a-zA-Z][a-zA-Z0-9_]*\z/.match?(@prepared_field) &&
             !(%w[record_id smiles supplier offer_id observed_at descriptors other_descriptors pattern_fingerprint] + DESCRIPTORS).include?(@prepared_field)
        raise Unsafe, 'invalid prepared SMILES field'
      end
      @fingerprint_field = 'morgan_' + Digest::SHA256.hexdigest(
        "morgan-r3-2048-lsb0-chiral0-features0-v1\0#{SPEC.fetch('rdkit_version')}\0#{SPEC.fetch('preparation_id')}"
      )
      raise Unsafe, 'conflicting prepared SMILES field' if @prepared_field == @fingerprint_field
      @chemistry = { 'spec' => config.fetch('spec'), 'descriptor_v1' => true, 'descriptor_layout' => 'nested',
                     'smiles_field' => 'smiles', 'prepared_smiles_field' => @prepared_field }
      @profile = { 'name' => 'native-descriptor-v1-nested-source-v1', 'chemistry' => @chemistry }
      @derived = [@prepared_field, @fingerprint_field, 'pattern_fingerprint', 'descriptors', 'other_descriptors'].freeze
    end

    def validate_input!(offer)
      raise Unsafe, 'caller supplied a derived chemistry field' unless (offer.keys & (@derived + DESCRIPTORS)).empty?
    end

    def configure_mapping!(mapping)
      mapping[:chemistry] = @chemistry
      mapping.fetch(:field_mappings).concat([
        { name: 'smiles', type: 'text', stored: true, indexed: false },
        { name: @prepared_field, type: 'text', stored: true, indexed: false, fast: true },
        { name: @fingerprint_field, type: 'bytes', stored: true, indexed: false, fast: true,
          input_format: 'hex', output_format: 'hex' },
        { name: 'pattern_fingerprint', type: 'bytes', stored: true, indexed: false,
          input_format: 'base64', output_format: 'base64' },
        { name: 'descriptors', type: 'json', stored: true, indexed: true, fast: true },
        { name: 'other_descriptors', type: 'json', stored: true, indexed: true }
      ])
    end

    def verify_source!(actual, expected)
      original = actual.reject { |name, _| @derived.include?(name) }
      raise Unsafe, 'offer membership or contents differ' unless original == expected
      prepared = actual[@prepared_field]
      raise Unsafe, 'missing or invalid prepared SMILES' unless prepared.is_a?(String) && !prepared.empty?
      fingerprint = actual[@fingerprint_field]
      unless fingerprint.is_a?(String) && /\A[0-9a-f]{512}\z/.match?(fingerprint) && fingerprint != '0' * 512
        raise Unsafe, 'missing or invalid derived Morgan fingerprint'
      end
      pattern = actual['pattern_fingerprint']
      begin
        valid_pattern = pattern.is_a?(String) && Base64.strict_decode64(pattern).bytesize == 256
      rescue ArgumentError
        valid_pattern = false
      end
      raise Unsafe, 'missing or invalid derived Pattern fingerprint' unless valid_pattern
      verify_descriptors!(actual['descriptors'])
      other = actual['other_descriptors']
      unless other.is_a?(Hash) && other.keys.sort == %w[scaffolds similarity_cluster] &&
             other['scaffolds'].is_a?(Array) && !other['scaffolds'].empty? &&
             other['scaffolds'].all? { |id| id.is_a?(Integer) && (-1...(1 << 63)).cover?(id) } &&
             other['similarity_cluster'].is_a?(Integer) && (0...10_000).cover?(other['similarity_cluster'])
        raise Unsafe, 'missing or invalid other descriptors'
      end
    end

    private

    def verify_descriptors!(descriptors)
      unless descriptors.is_a?(Hash) && descriptors.keys.sort == DESCRIPTORS.sort
        raise Unsafe, 'derived descriptor membership differs'
      end
      descriptors.each do |name, value|
        valid = if name.start_with?('Num', 'lipinski')
                  value.is_a?(Integer) && (-(1 << 63)...(1 << 63)).cover?(value)
                else
                  value.is_a?(Float) && value.finite?
                end
        raise Unsafe, 'invalid derived descriptor value' unless valid
      end
    end
  end
end
