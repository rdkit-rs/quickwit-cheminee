# frozen_string_literal: true
# Test acceptance guard only; not shipped as client behavior.
module LoadedJsonCheck
  def self.verify!(spec:, version:, features:, load_paths: $LOAD_PATH)
    raise 'Loaded JSON code version differs from activated spec' unless version == spec.version.to_s
    roots = [spec.full_gem_path, spec.extension_dir].select { |path| File.directory?(path) }.map { |path| File.realpath(path) }
    # Feature names are relative to load roots: faraday/request/json.rb is not JSON.
    paths = load_paths.map { |path| File.expand_path(path) }
    loaded = features.select do |path|
      paths.any? do |root|
        path == File.join(root, 'json.rb') ||
          (path.start_with?(File.join(root, 'json') + '/') && /\.(?:rb|so)\z/.match?(path))
      end
    end
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
