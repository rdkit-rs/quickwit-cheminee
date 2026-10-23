# Catalog journal recovery evidence

Sixteen focused tests / 86 assertions pass against the installed pre.contract1 gem,
using existing Ruby 3.3.8 and system JSON 2.7.2. This is deliberately separate from
the pinned SDK wire suite (JSON 3.1.0); it does not satisfy that suite's lock check.

The tests execute actual file replacement/fsync and child-process exits with a
file-backed fake server acceptance/call ledger. Parent and child observe the same
ledger, avoiding an in-memory fork copy being mistaken for evidence of no dispatch.
They cover intent-before-dispatch, accepted-before-ACK, saved ACK, failed ACK save,
sealed-before-pointer, pointer-before-final-state, stale and delayed promotion,
competing cooperating publishers, duplicate acknowledged batch, disjoint-batch
blocking after uncertainty, missing acknowledgement counts, uncertain index creation
and interrupted rollback without a second toggle or high-water regression. Owned test children are bounded and reaped on failure.

No production importer behavior changed. These checks support conservative local
recovery under an intact journal and shared cooperative flock; they do not prove
server write fencing, remote CAS, index immutability, server persistence, power-loss
survival, filesystem corruption recovery or distributed HA. No live index was created.

Pinned Ruby suite diagnosis: retained JSON extensions were built for the removed
Ruby container and require libruby.so.3.3; the existing onboarding Ruby provides
libruby-3.3.so.3.3 and uses a different RubyGems extension directory. An isolated
activation probe confirmed both barriers without altering installed metadata. Do not
symlink incompatible runtime names or weaken the lock check. Matching existing
runtime/extension artifacts are needed for a trustworthy pinned rerun.

Full workspace, Compose resource, representative-corpus and HA/durability gates
remain blocked by their recorded prerequisites. Publication hold remains intact.

Reproduce the focused suite in this retained workspace (no installation/build):

```sh
source /workspace/.onboarding/env.sh
export GEM_HOME=/workspace/recovery/ruby-dependencies/ruby/3.3.0
export GEM_PATH=$GEM_HOME:/workspace/.onboarding/sysroot/usr/lib/x86_64-linux-gnu/rubygems-integration/3.3.0:/workspace/.onboarding/sysroot/usr/share/rubygems-integration/all
ruby sdk/ruby/examples/catalog_generation_test.rb
```

The onboarding environment includes Cargo settings, but this command invokes only
Ruby. Do not reuse those Cargo settings to bypass campaign admission.

A resource-safe next route for the pinned suite is to transfer an already-built
JSON 3.1.0 gem installation from the successful worker's matching Ruby 3.3.8
environment, including extension files, gemspec, build-completion metadata, source
provenance and SHA256 manifest. Verify ELF dependencies and Ruby ABI before use,
place it in an isolated GEM_HOME, then rerun the unchanged lock-checking suite.
A matching Ruby runtime artifact is another option if already available. Neither
artifact is currently present; the retained Docker image alone is not a runnable
container. Image export/new-container creation remains unadmitted.
