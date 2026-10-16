# frozen_string_literal: true

require 'quickwit-cheminee'
require 'json'
require 'set'

module QuickwitCheminee
  # Explicit policy for exhaustive search over one immutable, unique-ID generation.
  # This does not make an index immutable or validate catalog-wide ID uniqueness.
  # It is opt-in composition over DefaultApi, not a Searchkick/global patch.
  class ExactSearch
    class IncompleteResponse < StandardError
      attr_reader :reason, :status, :request_id

      def initialize(reason, status:, request_id:)
        @reason, @status, @request_id = reason, status, request_id
        super("Search response rejected: #{reason}")
      end
    end

    attr_reader :generation

    def initialize(api:, generation:)
      unless generation.is_a?(String) && /\A[a-zA-Z][a-zA-Z0-9_.-]{2,254}\z/.match?(generation)
        raise ArgumentError, 'Use one concrete generation index ID (3..255 characters)'
      end
      @api = api
      @generation = generation.dup.freeze
    end

    # Offsets are bounded API requests, not snapshots or performance guidance.
    # Do not modify or delete/recreate the generation between page requests.
    def search(query:, limit: 20, offset: 0)
      raise ArgumentError, 'query must be a JSON object' unless query.is_a?(Hash)
      unless [limit, offset].all? { |v| v.is_a?(Integer) && v.between?(0, 10_000) } && limit + offset <= 10_000
        raise ArgumentError, 'limit and offset must be nonnegative integers with sum <= 10000'
      end
      # Round-trip to isolate input and reject non-JSON values before HTTP.
      body = JSON.parse(JSON.generate({query: json_value(query), size: limit, from: offset,
                                      track_total_hits: true,
                                      sort: [{_score: 'desc'}, {record_id: 'asc'}]}), symbolize_names: true)
      response, status, headers = @api.search_composable_unchecked_with_http_info(generation, body, allow_partial_search_results: false)
      validate_response!(response, limit, offset, status, headers)
      response
    end

    # The server's separate _count route does not report failed splits; never use it.
    def count(query:)
      search(query: query, limit: 0).fetch(:hits).fetch(:total).fetch(:value)
    end

    private

    def json_value(value, depth = 0)
      raise ArgumentError, 'Query nesting exceeds 100 levels' if depth > 100
      case value
      when Hash
        result = {}
        value.each do |key, child|
          unless key.is_a?(String) || key.is_a?(Symbol)
            raise ArgumentError, 'Query object keys must be strings or symbols'
          end
          name = key.to_s
          raise ArgumentError, 'Duplicate JSON query key' if result.key?(name)
          result[name] = json_value(child, depth + 1)
        end
        result
      when Array
        value.map { |child| json_value(child, depth + 1) }
      when String
        String.new(value)
      when Integer, TrueClass, FalseClass, NilClass
        value
      when Float
        raise ArgumentError, 'Query numbers must be finite' unless value.finite?
        value
      else
        raise ArgumentError, 'Query contains a non-JSON value'
      end
    end

    def nonnegative_integer?(value)
      value.is_a?(Integer) && value >= 0
    end

    def validate_response!(response, limit, offset, status, headers)
      request_id = headers['x-request-id']
      request_id = nil unless request_id.is_a?(String) && /\A[a-zA-Z0-9._:-]{1,128}\z/.match?(request_id)
      check = lambda do |condition, reason|
        raise IncompleteResponse.new(reason, status: status, request_id: request_id) unless condition
      end
      check.call(status == 200, :http_status)
      check.call(response.is_a?(Hash), :response_shape)
      check.call(response[:timed_out] == false, :timeout)
      check.call([nil, false].include?(response[:terminated_early]), :early_termination)
      check.call(response[:error].nil? && [nil, []].include?(response[:errors]), :server_errors)
      shards = response[:_shards]
      check.call(shards.is_a?(Hash), :shard_shape)
      check.call(%i[total successful skipped failed].all? { |key| nonnegative_integer?(shards[key]) }, :shard_counts)
      check.call(shards[:failed].zero? && shards[:skipped].zero? && shards[:successful] == shards[:total], :failed_or_skipped_shards)
      check.call([nil, []].include?(shards[:failures]), :shard_failures)
      hits = response[:hits]
      check.call(hits.is_a?(Hash) && hits[:total].is_a?(Hash) && hits[:hits].is_a?(Array), :hits_shape)
      check.call(hits[:total][:relation] == 'eq' && nonnegative_integer?(hits[:total][:value]), :total_shape)
      total = hits[:total][:value]
      check.call(total.zero? || shards[:total].positive?, :total_without_shards)
      check.call(hits[:hits].length == [limit, [total - offset, 0].max].min, :page_length)
      ids = Set.new
      previous = nil
      hits[:hits].each do |hit|
        check.call(hit.is_a?(Hash) && hit[:_index] == generation, :hit_index)
        tuple = hit[:sort]
        check.call(tuple.is_a?(Array) && tuple.length == 2, :sort_shape)
        score, id = tuple
        check.call(score.is_a?(Numeric) && score.finite? && nonnegative_integer?(id) && id < 2**64, :sort_values)
        check.call(hit[:_source].is_a?(Hash) && hit[:_source][:record_id].is_a?(Integer) && hit[:_source][:record_id] == id, :record_id)
        check.call(ids.add?(id), :duplicate_id)
        if previous
          check.call(previous[0] > score || (previous[0] == score && previous[1] < id), :sort_order)
        end
        previous = tuple
      end
    end
  end
end
