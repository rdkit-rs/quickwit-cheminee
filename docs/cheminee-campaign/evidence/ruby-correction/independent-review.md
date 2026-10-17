# Independent review: loaded JSON acceptance guard

Scoped verdict: accepted as a Linux test-acceptance guard. No blocking source finding remains. This review does not approve a local pinned wire-suite result or overall campaign readiness.

Reviewed working-tree files on base `7a87a0bd4db440f62217c11c3b9afb597777ed53`:

| File | SHA-256 |
| --- | --- |
| `sdk/ruby/loaded_json_check.rb` | `45fa962be83f415a35b5985c2b6b9484f74b53a33dda9107c6cc8d1eb71f8aa6` |
| `sdk/ruby/loaded_json_check_test.rb` | `4bfa749c82be948b3304217622e6dd7247da0ffb92019c1d2762c6973cfaa833` |
| `sdk/ruby/wire_test.rb` | `a5c171079e957978056bd64b8d868679ff8801d24b809701345725bffe90e5c5` |

The wire suite first compares activated dependency specifications with its unchanged lock, then compares actual `JSON::VERSION` with that specification and checks loaded JSON Ruby/native file provenance. Both native parser and generator plus `json.rb` are required. Every matching loaded JSON feature must resolve inside the activated gem or extension directory; canonical paths and directory boundaries prevent a symlink or similarly prefixed directory from passing accidentally. Missing files fail closed. These checks address the observed RUBYLIB shadowing without changing runtime behavior or dependency pins. They do not authenticate gem contents or prove loaded code provenance for other dependencies, which remain metadata checks. The required `.so` names target the Linux acceptance environment.

Independent execution of the final unit file with seed 10109 passed: **8 runs, 9 assertions, 0 failures, 0 errors, 0 skips**, 0.003261 seconds. This used onboard Ruby 3.3.8 and fixture files; it did not load JSON 3.1.0 native extensions. `git diff --check` passed.

Two additional checks used the actual onboard JSON 2.7.2 and its real loaded features against the retained JSON 3.1.0 gem specification:

1. Actual version 2.7.2 was rejected with `Loaded JSON code version differs from activated spec`.
2. Passing the matching claimed version 3.1.0 while retaining the actual system feature paths was rejected with `JSON loaded outside activated gem/extension roots`.

These checks establish that neither activated metadata nor a matching version parameter alone hides the observed shadowing. They are not HTTP or native JSON 3.1.0 runtime tests.

The corrected worker report is 6,228 bytes with SHA-256 `a3e12d8fb7750fee20f6f2e421e071ba9f60ad1d266b55bcee456b89d2a27fde`, matching the documentation. Its corrected 20-test/392-assertion result, seed 10109, belongs to worker commit `f6e64991dec0c3690b4c6b2324bca084330b28f1`; the original seed 704 pinned-JSON attribution is explicitly withdrawn. It is not a rerun of this integration tree or new guard.

Independently hashed local runtime files match the worker report:

- Ruby executable: `d23057791401d5687392c05b258a7e4fe1ebf85a447372ce11169b5e27cc3e2f`.
- Genuine `libruby-3.3.so.3.3.8`: `7c2d9793682780a5103814ec2401a4672479d3cb63bf2d52e3d0c9c4273d1e69`.

The remaining local artifact gap is the worker's matching JSON 3.1.0 gem/extension installation. A supported artifact containing the original Ruby files, metadata and native extensions is the smallest next input; inspect its real ELF dependencies and hashes in an isolated installation before a locked rerun with this guard. Matching executable/library hashes alone does not establish complete runtime portability. Do not substitute the older locally retained native extension, fabricate build markers, alias SONAMEs, or relax the lock. No transfer, installation, build, new container or ABI override was performed in this review.
