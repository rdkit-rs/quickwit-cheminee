# frozen_string_literal: true
# Real journal files plus a fake wire peer. No HTTP, native, durability or scale claim.
require 'minitest/autorun'
require 'tmpdir'
require_relative 'catalog_generation'
require_relative 'catalog_test_peer'

class CatalogPartitionedAuditTest < Minitest::Test
  include CatalogTestJournal

  def sparse_ids
    [0] + (1...10_000).map { |number| (1 << 53) + number * 97 } + [(1 << 64) - 1]
  end

  def test_more_than_ten_thousand_sparse_u64_ids_cover_domain_without_oversized_offset
    generation = ready(sparse_ids)
    assert_equal generation, @store.promote(generation)
    assert_equal generation, @store.verify_active.fetch('active')
    ranges = @api.requests.select { |body| body[:size].zero? && body[:query][:range] }
    assert_equal [{ gte: 0, lte: (1 << 64) - 2 }, { gte: (1 << 64) - 1, lte: (1 << 64) - 1 }],
                 ranges.first(2).map { |body| body[:query][:range][:record_id] }
    assert @api.requests.all? { |body| body[:from] + body[:size] <= 10_000 }
    assert @api.requests.any? { |body| body[:from] == 9900 && body[:size] == 100 }
  end

  def test_exact_partition_boundary_has_one_range_and_last_full_page
    generation = ready((1..10_000).to_a)
    @store.promote(generation)
    counts = @api.requests.select { |body| body[:size].zero? && body[:query][:range] }
    assert_equal 1, counts.length
    assert_equal({ gte: 0, lte: (1 << 64) - 1 }, counts.first[:query][:range][:record_id])
    assert_equal [9900, 100], @api.requests.last(2).first.values_at(:from, :size)
  end

  def test_same_count_duplicate_at_page_boundary_and_missing_id_cannot_promote
    generation = ready((1..101).to_a)
    @api.rows[generation][-1] = @api.rows[generation][-2].dup
    rejected_promotion(generation)
  end

  def test_same_count_extra_in_sparse_gap_replacing_missing_record_cannot_promote
    generation = ready([10, 100, (1 << 64) - 2])
    @api.rows[generation][1]['record_id'] = 50
    rejected_promotion(generation)
  end

  def test_extra_record_outside_expected_min_and_max_is_counted
    generation = ready([10, 100])
    @api.rows[generation] << @api.rows[generation][0].merge('record_id' => (1 << 64) - 1)
    rejected_promotion(generation)
  end

  def test_partition_boundary_missing_row_replaced_by_gap_row_fails
    ids = sparse_ids
    generation = ready(ids)
    @api.rows[generation][-1]['record_id'] -= 1
    rejected_promotion(generation)
  end

  def test_missing_row_and_altered_original_contents_fail
    [:missing, :altered, :extra_field].each_with_index do |fault, index|
      generation = ready([10, 100], sequence: index + 1)
      case fault
      when :missing then @api.rows[generation].pop
      when :altered then @api.rows[generation][0]['price'] = 11
      when :extra_field then @api.rows[generation][0]['unexpected'] = true
      end
      rejected_promotion(generation)
    end
  end

  def test_changed_page_total_and_final_global_count_fail
    [:page_total, :final_count].each_with_index do |fault, index|
      generation = ready([10, 100], sequence: index + 1)
      global_counts = 0
      @api.mutate_response = lambda do |response, body|
        global_counts += 1 if body[:query][:match_all]
        if (fault == :page_total && body[:size].positive?) || (fault == :final_count && global_counts == 2)
          response[:hits][:total][:value] += 1
        end
      end
      rejected_promotion(generation)
    end
  end

  def test_strict_adapter_rejects_partial_timeout_inexact_total_and_short_page
    [:failed_shard, :timeout, :inexact, :short_page].each_with_index do |fault, index|
      generation = ready([1, 2], sequence: index + 1)
      @api.mutate_response = lambda do |response, body|
        case fault
        when :failed_shard then response[:_shards][:failed] = 1
        when :timeout then response[:timed_out] = true
        when :inexact then response[:hits][:total][:relation] = 'gte'
        when :short_page then response[:hits][:hits].pop if body[:size].positive?
        end
      end
      rejected_promotion(generation)
    end
  end

  def test_disjoint_batch_membership_and_acknowledged_retries_remain_guarded
    generation = @store.stage(manifest([0, 1, (1 << 64) - 1]))
    @store.ingest(generation, batch_id: 'first', record_ids: [0, 1])
    assert_raises(CatalogGeneration::Unsafe) { @store.ingest(generation, batch_id: 'second', record_ids: [1, (1 << 64) - 1]) }
    assert_raises(CatalogGeneration::Unsafe) { @store.ingest(generation, batch_id: 'duplicate', record_ids: [1, 1]) }
    assert_raises(CatalogGeneration::Unsafe) { @store.ingest(generation, batch_id: 'unknown', record_ids: [2]) }
    assert_equal({ 'accepted' => 2, 'rejected' => 0 }, @store.ingest(generation, batch_id: 'first', record_ids: [1, 0]))
    assert_equal 1, @api.ingest_bodies.length
    @store.ingest(generation, batch_id: 'second', record_ids: [(1 << 64) - 1])
    assert_equal generation, @store.promote(generation)
  end
end
