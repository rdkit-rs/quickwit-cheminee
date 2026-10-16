# frozen_string_literal: true
# Test acceptance guard only; not shipped as client behavior.
module LoadedJsonCheck
  def self.verify!(spec:, version:, features:)
    raise 'Loaded JSON code version differs from activated spec' unless version == spec.version.to_s
    roots = [spec.full_gem_path, spec.extension_dir].select { |path| File.directory?(path) }.map { |path| File.realpath(path) }
    expected = %r{(?:\A|/)json(?:\.rb|/.*\.(?:rb|so))\z}
    loaded = features.select { |path| expected.match?(path) }
    required = ['json.rb', 'json/ext/parser.so', 'json/ext/generator.so']
    required.each do |suffix|
      raise "Missing loaded JSON feature: #{suffix}" unless loaded.any? { |path| path.end_with?("/#{suffix}") }
    end
    loaded.each do |path|
      actual = File.realpath(path)
      raise 'JSON loaded outside activated gem/extension roots' unless roots.any? { |root| actual.start_with?(root + '/') }
    end
    true
  end
end
