# Corrected Ruby worker attribution

The original worker seed 704 result (20 tests/392 assertions) used JSON 2.7.2 despite
an activated JSON 3.1.0 gem specification. Its pinned-JSON claim is withdrawn.
The original report is retained as historical evidence, not current acceptance.

The corrected worker report was read completely from Library
`libfile_b20bef2f6d3481918406e163236bb8f3` and its 6,228-byte content SHA256 matched
`a3e12d8fb7750fee20f6f2e421e071ba9f60ad1d266b55bcee456b89d2a27fde`.
It reports 20 tests/392 assertions passing with actual JSON 3.1.0, seed 10109,
on worker commit f6e64991dec0c3690b4c6b2324bca084330b28f1. It prepends activated
require paths and checks JSON::VERSION and loaded features. This is corrected
worker evidence, not a local rerun or acceptance of later source changes.

Our existing Ruby3.3.8 executable and genuine libruby-3.3.so.3.3.8 hashes exactly
match the worker report. The locally retained JSON3.1.0 extensions instead require
libruby.so.3.3; the compatible worker extension bytes are absent. Matching two
runtime hashes narrows the artifact gap, but does not prove whole-runtime or
extension portability. No binary transfer, install, build, new container or ABI
alias was attempted.

Smallest next step: obtain a supported, hashed artifact of the worker's JSON3.1.0
gem/extension installation (parser and generator plus its Ruby files and metadata).
Verify against the reported extension hashes and inspect real ELF dependencies;
use an isolated GEM_HOME with the genuine matching runtime, explicitly prefer its
require paths, and run the unchanged dependency lock plus the strengthened guard.
Do not rename libraries, fabricate build markers or accept a version string alone.

The wire test now checks actual JSON::VERSION and requires JSON Ruby/native loaded
features to resolve inside the activated gem or extension root. Eight focused tests (nine assertions)
cover positive roots, version mismatch, missing parser, shadowed Ruby and external
symlink rejection. They use empty fixture files to test the guard, not a JSON3.1.0
runtime or transport. Other dependency metadata checks remain metadata checks.

Catalog journal tests remain separately attributed to systemJSON2.7.2. Full workspace,
live Compose, representative data and HA/durability gates stay open. Publication hold
remains intact.
