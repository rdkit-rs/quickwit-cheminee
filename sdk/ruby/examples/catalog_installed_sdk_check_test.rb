# frozen_string_literal: true
require 'minitest/autorun'
require 'tmpdir'
require 'fileutils'
require_relative 'catalog_installed_sdk_check'

class CatalogInstalledSdkCheckTest < Minitest::Test
  Spec = Struct.new(:full_gem_path)

  def setup
    @temporary = Dir.mktmpdir('catalog-installed-sdk-')
    @spec = Spec.new(File.join(@temporary, 'gems', 'quickwit-cheminee-0.9.1.pre.pilot.g12345678'))
    @features = %w[quickwit-cheminee.rb quickwit-cheminee/exact_search.rb quickwit-cheminee/api/default_api.rb].map do |name|
      write_feature(File.join(@spec.full_gem_path, 'lib', name))
    end
    @checkout = File.join(@temporary, 'home', 'runner', 'work', 'quickwit-cheminee', 'quickwit-cheminee')
  end

  def teardown
    FileUtils.remove_entry(@temporary)
  end

  def write_feature(path)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, '')
    path
  end

  def check(features = @features)
    CatalogInstalledSdkCheck.verify!(spec: @spec, features: features)
  end

  def test_checkout_named_quickwit_cheminee_does_not_make_examples_sdk_code
    examples = %w[catalog_generation.rb catalog_native_oracle.rb catalog_native_smoke.rb].map do |name|
      write_feature(File.join(@checkout, 'sdk', 'ruby', 'examples', name))
    end
    assert check(@features + examples)
  end

  def test_genuine_sdk_library_outside_installed_root_is_rejected
    shadow = write_feature(File.join(@checkout, 'sdk', 'ruby', 'generated', 'lib', 'quickwit-cheminee', 'models', 'fingerprint_spec.rb'))
    assert_raises(RuntimeError) { check(@features + [shadow]) }
  end

  def test_both_required_library_entrypoints_must_be_present
    @features.first(2).each do |required|
      assert_raises(RuntimeError) { check(@features - [required]) }
    end
  end

  def test_symlink_inside_gem_cannot_hide_external_sdk_code
    external = write_feature(File.join(@temporary, 'external.rb'))
    File.unlink(@features.last)
    File.symlink(external, @features.last)
    assert_raises(RuntimeError) { check }
  end

  def test_root_prefix_is_not_directory_membership
    shadow = write_feature(File.join(@spec.full_gem_path + '-other', 'lib', 'quickwit-cheminee', 'models', 'fingerprint_spec.rb'))
    assert_raises(RuntimeError) { check(@features + [shadow]) }
  end

  def test_missing_loaded_library_file_fails_closed
    File.unlink(@features.last)
    assert_raises(Errno::ENOENT) { check }
  end
end
