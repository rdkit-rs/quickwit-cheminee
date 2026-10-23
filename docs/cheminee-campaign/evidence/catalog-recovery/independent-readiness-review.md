# Independent review: local catalog recovery tests

Verdict: acceptable within the documented local-journal, fake-peer scope. No remaining blocking finding in the test addition. This is not approval of server persistence, chemistry, HTTP behavior, power-loss durability, the pinned SDK suite, or campaign readiness.

Reviewed file: `sdk/ruby/examples/catalog_generation_test.rb`

SHA-256: `5038f8c2a0be8af8e3ae72d555a250db1bff4355eca1ab9b7dfddd1bcfbee5de`

Independent execution with seed 1129 completed in 0.054328 seconds: **16 runs, 86 assertions, 0 failures, 0 errors, 0 skips**. `git diff --check` also passed. Source changes were not made by this reviewer.

The shared file-backed peer ledger makes child acceptance and call counts observable by the parent, addressing fork copy-on-write false oracles. The suite covers interruption before dispatch, after acceptance, after acknowledgement persistence, before and after pointer publication, delayed/stale promotion, missing acceptance counts, lost create acknowledgement, acknowledgement persistence failure, disjoint-batch blocking after uncertainty, cooperating publishers, and interrupted rollback. Owned children are reaped and killed on timeout where needed. The publisher test exercises a bounded two-process schedule, not exhaustive interleavings.

The README accurately limits these results to recovery decisions with readable, intact local journal files and cooperating callers. It does not equate process exit with power loss, or a fake peer's fsync with actual server durability. Direct writes and stale index cleanup remain outside this protocol's guarantees.

## Reproduction and runtime attribution

From `/workspace/quickwit-cheminee-pr3-inspection`:

```bash
source /workspace/.onboarding/env.sh
export GEM_HOME=/workspace/recovery/ruby-dependencies/ruby/3.3.0
export GEM_PATH=$GEM_HOME:/workspace/.onboarding/sysroot/usr/lib/x86_64-linux-gnu/rubygems-integration/3.3.0:/workspace/.onboarding/sysroot/usr/share/rubygems-integration/all
ruby sdk/ruby/examples/catalog_generation_test.rb --seed 1129
```

Observed runtime: Ruby 3.3.8, architecture `x86_64-linux-gnu`, JSON 2.7.2, installed `quickwit-cheminee` 0.9.1.pre.contract1. JSON native extensions load from the onboard sysroot, not the retained JSON 3.1.0 gem. The interpreter warns that the retained JSON 3.1.0 extensions are not built for this environment. This pass must not be attributed to `sdk/ruby/Gemfile.lock`.

## Pinned-suite blocker and retained artifact route

The retained JSON 3.1.0 extensions under `ruby-dependencies/ruby/3.3.0/extensions/x86_64-linux/3.3.0` depend on `libruby.so.3.3` and were built in the removed Ruby 3.3.6 image environment. The available onboard Ruby 3.3.8 uses `libruby-3.3.so.3.3` and extension architecture `x86_64-linux-gnu`. Its bundled JSON 2.7.2 does not satisfy the pinned suite's dependency assertions. JSON 3.1.0 has no usable MRI pure-Ruby parser fallback in the retained artifact.

Inventory found only the existing native builder container, with no independent Ruby installation (the shared onboarding sysroot can still be invoked inside it). The retained `ruby:3.3.6-bookworm` image and `.pre.contract1` gem remain potential inputs to a later matching-runtime rerun; there is no supported callable Ruby runtime in that image without restoring a container or exporting its filesystem. Both are outside the current disk/headroom constraints. Rebuilding JSON for the onboard runtime would also violate the current no-build constraint and require separate environment attribution.

Preserve the test source, this review, the parent's `catalog-recovery-tests-final.log`, the pinned gem and lockfile, and the retained image for the next admitted runtime phase. Do not manufacture extension markers, change SONAME links, force an ABI, relax the dependency assertions, or describe the onboard JSON pass as a pinned-suite rerun. No builds, new containers, exports, ABI overrides, or network work were performed during this review.
