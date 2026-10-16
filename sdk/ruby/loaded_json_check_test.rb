# frozen_string_literal: true
require 'minitest/autorun'
require 'tmpdir'
require 'fileutils'
require_relative 'loaded_json_check'

class LoadedJsonCheckTest < Minitest::Test
  Spec = Struct.new(:version, :full_gem_path, :extension_dir)
  def setup
    @directory = Dir.mktmpdir('json-provenance-')
    @spec = Spec.new('3.1.0', File.join(@directory, 'gem'), File.join(@directory, 'extensions'))
    @features = %w[json.rb json/ext/parser.so json/ext/generator.so].map do |name|
      path = File.join(@spec.full_gem_path, 'lib', name)
      FileUtils.mkdir_p(File.dirname(path)); File.write(path, '')
      path
    end
  end
  def teardown
    FileUtils.remove_entry(@directory)
  end
  def check(version: '3.1.0', features: @features)
    LoadedJsonCheck.verify!(spec: @spec, version: version, features: features,
      load_paths: [File.join(@spec.full_gem_path, 'lib'), @spec.extension_dir, @directory, @spec.full_gem_path + '-other/lib'])
  end
  def test_matching_code_roots
    assert check
  end
  def test_activated_spec_does_not_mask_wrong_code_version
    assert_raises(RuntimeError) { check(version: '2.7.2') }
  end
  def test_missing_native_parser
    assert_raises(RuntimeError) { check(features: @features.reject { |p| p.end_with?('parser.so') }) }
  end
  def test_shadowed_ruby_code_with_matching_version
    shadow = File.join(@directory, 'json.rb'); File.write(shadow, '')
    assert_raises(RuntimeError) { check(features: [shadow] + @features.drop(1)) }
  end
  def test_symlink_cannot_hide_external_native_code
    external = File.join(@directory, 'external.so'); File.write(external, '')
    File.unlink(@features[1]); File.symlink(external, @features[1])
    assert_raises(RuntimeError) { check }
  end
  def test_extension_root_is_supported
    FileUtils.mkdir_p(@spec.extension_dir)
    @features[1..].each do |path|
      destination = File.join(@spec.extension_dir, path.split('/lib/').last)
      FileUtils.mkdir_p(File.dirname(destination)); FileUtils.mv(path, destination)
      @features[@features.index(path)] = destination
    end
    assert check
  end
  def test_missing_generator_and_missing_file_are_rejected
    assert_raises(RuntimeError) { check(features: @features.reject { |p| p.end_with?('generator.so') }) }
    File.unlink(@features[1])
    assert_raises(Errno::ENOENT) { check }
  end
  def test_root_prefix_is_not_directory_membership
    shadow = @spec.full_gem_path + '-other/lib/json.rb'
    FileUtils.mkdir_p(File.dirname(shadow)); File.write(shadow, '')
    assert_raises(RuntimeError) { check(features: [shadow] + @features.drop(1)) }
  end

  def test_faraday_json_middleware_is_not_json_implementation
    middleware = File.join(@directory, 'faraday/request/json.rb')
    FileUtils.mkdir_p(File.dirname(middleware)); File.write(middleware, '')
    assert check(features: @features + [middleware])
  end

end
