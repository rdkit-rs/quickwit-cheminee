# Independent review: local JSON 3.1.0 acceptance

Scoped verdict: the local pinned-Ruby runtime blocker is closed for the observed installed-gem wire run. The corrected JSON feature selector, isolated-runtime script and transferred files support this result. This is not new server, durability, Compose, full-workspace or publication approval.

Independent reruns through `/workspace/recovery/run-pinned-ruby.sh`, seed 10109:

- `sdk/ruby/wire_test.rb`: **20 runs, 392 assertions, 0 failures, 0 errors, 0 skips**, 0.305483 seconds.
- `sdk/ruby/loaded_json_check_test.rb`: **9 runs, 10 assertions, 0 failures, 0 errors, 0 skips**, 0.004241 seconds.

Both invocations reported Ruby 3.3.8 and actual JSON 3.1.0, with parser and generator loaded from `/workspace/recovery/json31-isolated/gems/json-3.1.0/lib/json/ext/`. The script verifies canonical native paths and a Unicode/full-u64 round trip before loading the requested test file. The wire suite then checks the unchanged activated dependency lock and actual JSON Ruby/native provenance. Other dependencies' checks remain activated-spec checks.

The previous guard's basename matching incorrectly classified Faraday's request/response `json.rb` middleware as the JSON implementation. Feature names are now identified relative to the process's load roots, preserving the middleware while checking JSON's top-level entry and nested implementation files. The new regression and actual full wire run cover this previously untested interaction. Version mismatch, missing native files, wrong roots, prefix collisions and symlink escapes remain covered. These checks are scoped to the observed Linux load environment; they do not authenticate arbitrary future load-path changes or altered file contents.

Independently verified every one of the manifest's **33 files** against its recorded size and SHA-256, with exact file-set agreement and no symlink among the manifested files. Both native extension hashes match the corrected worker report. `readelf` confirms both require genuine `libruby-3.3.so.3.3`, `libm.so.6` and `libc.so.6`; no SONAME alias was used. The interpreter and genuine libruby hashes were independently matched to the worker report in the preceding correction review. No compilation, installation, new container or export was performed by this review.

Reviewed file hashes:

| File | SHA-256 |
| --- | --- |
| `sdk/ruby/loaded_json_check.rb` | `362787e50182c14df0da098bba7a0788f9556e4bf43ebbe5fffaa14a270a5369` |
| `sdk/ruby/loaded_json_check_test.rb` | `be9653c36313e0069758b6d4375005def50ffbabdc9a6b0e4d7646198bb251d5` |
| `sdk/ruby/wire_test.rb` | `7176084fcfed509b26e4ca0e8806aa113bd26ffc16fdf6ee2cce4eb5d18d6faa` |
| `run-pinned-ruby.sh` | `07041f3f9f52473b4de22ad72f566833863f8bbc2520da85a0cda3c12aa83e6d` |

`git diff --check` passed. Independent outputs are retained as `independent-wire.log` and `independent-guard.log` beside this review. The integrator's journal and native smoke logs are separate evidence and were not rerun by this reviewer in this task. No test totals are combined into a unique coverage count.
