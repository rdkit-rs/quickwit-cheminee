# frozen_string_literal: true

# Requires the disposable fixtures from tantivy-rdkit/poc/composable.py and
# their restarted services. Read-only: no benchmark or HA claims follow.
gem 'quickwit-cheminee', ENV.fetch('SDK_EXPECTED_VERSION', '0.9.1.pre.contract1')
require 'quickwit-cheminee'
require 'quickwit-cheminee/exact_search'
require 'json'

fixtures = JSON.parse(File.read(File.join(ENV.fetch('SDK_NATIVE_FIXTURES'), 'results.json')), symbolize_names: true)
raise 'Fixture harness did not pass' unless fixtures[:status] == 'passed'
config = QuickwitCheminee::Configuration.new
config.scheme = 'http'
config.host = ENV.fetch('SDK_SMOKE_HOST')
config.base_path = ''
config.timeout = 60
api = QuickwitCheminee::DefaultApi.new(QuickwitCheminee::ApiClient.new(config))
raise 'Node not ready' unless api.ready
checks = []
topk_cases = fixtures[:checks].select { |check| check[:distributed_topk] }
failure_cases = fixtures[:checks].select { |check| check[:leaf_verification_failure] }
raise 'Wrong top-k operators' unless topk_cases.map { |c| c[:distributed_topk].keys }.sort == [[:molecular_graph], [:tanimoto]]
raise 'Wrong failure operators' unless failure_cases.map { |c| c[:leaf_verification_failure].keys }.sort == [[:fingerprint_contains], [:tanimoto]]

topk_cases.each do |check|
  query = check.fetch(:distributed_topk)
  exact = QuickwitCheminee::ExactSearch.new(api: api, generation: 'composable-topk')
  complete = exact.search(query: query, limit: 20)
  expected = complete[:hits][:hits].map { |hit| hit[:sort][1] }
  raise 'Independent expected top-k membership differs' unless expected.sort == (1..12).to_a + (101..104).to_a
  raise 'Independent expected tied prefix differs' unless expected.first(12) == (1..12).to_a
  raise 'Strict native count differs' unless exact.count(query: query) == 16
  pages = (0..16).step(3).flat_map do |offset|
    exact.search(query: query, limit: 3, offset: offset)[:hits][:hits].map { |hit| hit[:sort][1] }
  end
  raise 'Frozen offset enumeration differs' unless pages == expected && pages.uniq.length == 16
  checks << {operator: query.keys.first, count: 16, page_size: 3, enumerated_ids: pages}
end

failure_cases.each do |check|
  query = check.fetch(:leaf_verification_failure)
  exact = QuickwitCheminee::ExactSearch.new(api: api, generation: 'composable-leaf-failure')
  [:search, :count].each do |method|
    begin
      exact.public_send(method, query: query)
      raise "#{method} accepted failed native leaf"
    rescue QuickwitCheminee::ApiError => error
      raise 'Unexpected strict error status' unless error.code == 500
      raise 'Wrong strict failure cause' unless error.response_body.include?('indexed fingerprint must contain exactly 256 bytes')
    end
  end
  raw = api.search_composable_unchecked('composable-leaf-failure',
    {query: query, size: 20, track_total_hits: true, sort: [{_score: 'desc'}, {record_id: 'asc'}]}, allow_partial_search_results: true)
  raise 'Expected partial-result trap missing' unless raw[:_shards].values_at(:failed, :successful, :total) == [1, 1, 2] && raw[:hits][:total] == {value: 2, relation: 'eq'}
  raise 'Healthy partial hits differ' unless raw[:hits][:hits].map { |hit| hit[:_source][:record_id] } == [1, 2]
  checks << {operator: query.keys.first, strict_search_status: 500, strict_count_status: 500,
             unchecked_failed_splits: 1, unchecked_total_relation: 'eq'}
end
raise 'Missing fixture coverage' unless checks.length == 4
puts JSON.generate(status: 'passed', scope: 'installed gem against restarted native distributed fixtures', checks: checks)
