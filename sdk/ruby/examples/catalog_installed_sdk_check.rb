# frozen_string_literal: true

# Acceptance guard only. Match library paths so a checkout named quickwit-cheminee
# does not turn importer/example files into apparent SDK implementation files.
module CatalogInstalledSdkCheck
  def self.verify!(spec:, features:)
    gem_root = File.realpath(spec.full_gem_path) + '/'
    loaded = features.select { |path| %r{/lib/quickwit-cheminee(?:\.rb|/.*\.rb)\z}.match?(path) }
    unless loaded.any? { |path| path.end_with?('/lib/quickwit-cheminee.rb') } &&
           loaded.any? { |path| path.end_with?('/lib/quickwit-cheminee/exact_search.rb') } &&
           loaded.all? { |path| File.realpath(path).start_with?(gem_root) }
      raise 'SDK code loaded outside its installed gem'
    end
    true
  end
end
