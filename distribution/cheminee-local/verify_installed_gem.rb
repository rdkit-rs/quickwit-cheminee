# frozen_string_literal: true

# Inspect the supplied local archive and prove its installed files match before
# the live acceptance process activates this exact version outside generated code.
require 'rubygems/package'
require 'zlib'
require 'digest'
require 'json'

archive, expected, install_root = ARGV
raise 'Unexpected Ruby load overrides' unless [ENV['RUBYLIB'], ENV['RUBYOPT']].all? { |value| value.nil? || value.empty? }
package = Gem::Package.new(archive)
package.verify
raise 'Unexpected gem identity' unless package.spec.name == 'quickwit-cheminee' && package.spec.version.to_s == expected
gem 'quickwit-cheminee', expected
require 'quickwit-cheminee'
require 'quickwit-cheminee/exact_search'
installed = Gem.loaded_specs.fetch('quickwit-cheminee')
root = File.realpath(installed.full_gem_path)
raise 'Gem loaded outside the isolated installation' unless root.start_with?(File.realpath(install_root) + '/')
raise 'Activated gem version differs' unless installed.version.to_s == expected && QuickwitCheminee::VERSION == expected
files = {}
File.open(archive, 'rb') do |outer|
  Gem::Package::TarReader.new(outer) do |entries|
    entries.each do |entry|
      next unless entry.full_name == 'data.tar.gz'
      Zlib::GzipReader.wrap(entry) do |decompressed|
        Gem::Package::TarReader.new(decompressed) do |contents|
          contents.each do |file|
            next if file.directory?
            raise 'Unexpected gem member type' unless file.file?
            name = file.full_name
            raise 'Unsafe or duplicate gem member' if name.start_with?('/') || name.split('/').include?('..') || files.key?(name)
            target = File.realpath(File.join(root, name))
            raise 'Installed file escapes gem root' unless target.start_with?(root + '/')
            checksum = Digest::SHA256.hexdigest(file.read)
            raise "Installed file differs from gem archive: #{name}" unless Digest::SHA256.file(target).hexdigest == checksum
            files[name] = checksum
          end
        end
      end
    end
  end
end
raise 'Gem archive file list differs from specification' unless files.keys.sort == package.spec.files.sort
loaded = $LOADED_FEATURES.select { |path| path.end_with?('/lib/quickwit-cheminee.rb') || path.include?('/lib/quickwit-cheminee/') }
raise 'No SDK code loaded' if loaded.empty?
raise 'SDK code loaded outside installed gem' unless loaded.all? { |path| File.realpath(path).start_with?(root + '/') }
puts JSON.generate(gem_sha256: Digest::SHA256.file(archive).hexdigest, version: expected,
                   installed_root: root, installed_files: files.length,
                   installed_files_sha256: Digest::SHA256.hexdigest(JSON.generate(files.sort.to_h)))
