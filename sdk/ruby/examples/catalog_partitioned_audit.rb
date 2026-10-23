# frozen_string_literal: true

class CatalogGeneration
  # Range partitions cover the whole u64 domain, including gaps and both endpoints.
  # They bound each offset request; they do not provide a cursor or a write fence.
  class PartitionedAudit
    MAX_PARTITION_DOCS = 10_000
    PAGE_SIZE = 100
    MAX_RECORD_ID = (1 << 64) - 1

    def initialize(api:, state:, preparation: nil)
      @exact = QuickwitCheminee::ExactSearch.new(api: api, generation: state.fetch('generation'))
      @records = state.fetch('records')
      @preparation = preparation
    end

    def verify!
      query = { match_all: {} }
      raise Unsafe, 'published count mismatch' unless @exact.count(query: query) == @records.length
      return if @records.empty?

      lower = 0
      @records.each_slice(MAX_PARTITION_DOCS).with_index do |partition, index|
        following = @records[(index + 1) * MAX_PARTITION_DOCS]
        upper = following ? following.fetch('record_id') - 1 : MAX_RECORD_ID
        range = { range: { record_id: { gte: lower, lte: upper } } }
        verify_partition!(partition, range)
        lower = upper + 1
      end
      raise Unsafe, 'published count changed during audit' unless @exact.count(query: query) == @records.length
    end

    private

    def verify_partition!(partition, query)
      expected_count = partition.length
      raise Unsafe, 'partition count mismatch' unless @exact.count(query: query) == expected_count
      partition.each_slice(PAGE_SIZE).with_index do |expected_page, page|
        response = @exact.search(query: query, limit: expected_page.length, offset: page * PAGE_SIZE, order: :record_id)
        hits = response.fetch(:hits)
        raise Unsafe, 'partition count changed during audit' unless hits.fetch(:total).fetch(:value) == expected_count
        hits.fetch(:hits).zip(expected_page).each do |hit, expected|
          actual = JSON.parse(JSON.generate(hit.fetch(:_source)))
          if @preparation
            @preparation.verify_source!(actual, expected)
          elsif actual != expected
            raise Unsafe, 'offer membership or contents differ'
          end
        end
      end
    end
  end
end
