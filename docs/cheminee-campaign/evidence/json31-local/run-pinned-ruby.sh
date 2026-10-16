#!/bin/bash
set -euo pipefail
source /workspace/.onboarding/env.sh
export GEM_HOME=/workspace/recovery/json31-isolated
export GEM_PATH=$GEM_HOME:/workspace/recovery/ruby-dependencies/ruby/3.3.0:/workspace/.onboarding/sysroot/usr/share/rubygems-integration/all
export SDK_INSTALL_ROOT=/workspace/recovery/ruby-dependencies/ruby/3.3.0
export LEGACY_CHEMINEE_LIB=/workspace/cheminee-ruby/lib
cd /workspace/quickwit-cheminee-pr3-inspection
ruby -e 'gem "json", "3.1.0"; gem "logger", "1.7.0"; gem "timeout", "0.6.1"; gem "uri", "1.1.2"; gem "net-protocol", "0.4.0"; gem "net-http", "0.10.0"; $LOAD_PATH.unshift(*Gem.loaded_specs.values.flat_map(&:full_require_paths)); require "json"; abort "wrong JSON" unless JSON::VERSION == "3.1.0"; paths=$LOADED_FEATURES.grep(%r{/json/ext/.*\.so$}); abort "wrong native paths" unless paths.size==2 && paths.all? {|p| File.realpath(p).start_with?(ENV.fetch("GEM_HOME")+"/")}; x={"id"=>18446744073709551615,"label"=>"東京"}; abort "roundtrip" unless JSON.parse(JSON.generate(x))==x; puts JSON.generate(ruby:RUBY_VERSION,json:JSON::VERSION,native_paths:paths); load ARGV.shift' "$@"
