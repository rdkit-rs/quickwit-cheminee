# Native contract evidence

This is small-fixture functional evidence on amd64, not a performance, HA or
catalog-refresh result. The runtime API source is `a52146c8fe2967af57308a3774c20c3b817ae8ac`;
later campaign commits add tests/documentation. RDKit and builder identity are in
`validation.json`. The installed gem's SHA-256 remains the recorded candidate hash.

The fresh broader native suites passed 229 document-mapper tests and 178 server
tests. These overlap earlier test totals; do not add them into a unique test count.
`native-clippy.log` records the successful command, run from `quickwit/`:

```sh
cargo clippy -p quickwit-serve -p quickwit-doc-mapper \
  --features quickwit-serve/native-chemistry --lib -- -D warnings
```

With native prerequisites installed, build the CLI and run the recovered harness
from `quickwit/`. The work directory must not already exist:

```sh
cargo build -p quickwit-cli --features native-chemistry --bin quickwit
python3 tantivy-rdkit/poc/composable.py \
  --binary target/debug/quickwit --work-dir /tmp/composable-native
```

It starts three local processes, checks 16 HTTP cases, then stops those processes.
The generated configurations, fixture indexes and `results.json` remain in the
work directory. Our retained work directory is
`/workspace/recovery/composable-native-run1`; results are copied here as
`native-http-results.json`. The two leaf request counters were both exercised.

Restart the same configurations and roles to check graceful persistence:

```sh
target/debug/quickwit run --config /tmp/composable-native/root.json \
  --service metastore --service control-plane --service indexer --service janitor
# Separate terminals, same network/filesystem:
target/debug/quickwit run --config /tmp/composable-native/leaf-a.json --service searcher
target/debug/quickwit run --config /tmp/composable-native/leaf-b.json --service searcher
```

Wait for three ready nodes at `GET http://127.0.0.1:19480/api/v1/cluster`.
Install the candidate gem with its locked dependencies, then run outside the
generated source load path (set GEM_HOME/GEM_PATH if using an isolated install):

```sh
SDK_SMOKE_HOST=127.0.0.1:19480 \
SDK_NATIVE_FIXTURES=/tmp/composable-native \
SDK_EXPECTED_VERSION=0.9.1.pre.dsl \
ruby sdk/ruby/native_smoke.rb
```

`ruby-native-restart.log` records complete graph/Tanimoto enumeration of 16 known
IDs in pages of three, counts, and strict search/count rejection of malformed
fingerprints. The unchecked method confirms healthy IDs `[1,2]`, one successful
and one failed split, yet total `2` with relation `eq`. Tests check the specific
failure cause without printing raw response bodies. These are frozen `no_merge`
indexes; no conclusion about concurrent writes, merges or cursor behavior follows.

## Known failing requirement

`sibling-domain-probe.json` records a live counterexample using the same malformed
fingerprint fixture. The unbounded Tanimoto query returns HTTP 500. Wrapping it in
`{"bool":{"must":[QUERY,{"match_none":{}}]}}` returns HTTP 200, exact zero and
zero failed splits. This violates the requested stronger rule that adjacent
Boolean filters must not hide verification errors. Explicit numeric candidates restricting
`record_id` to `[0,2]` correctly return exact two; that intentionally narrows the
verification domain. The adapter does not repair the sibling case. It remains a
release blocker for that guarantee.

The cluster shares one host and a local filesystem; graceful process restart is
not crash durability, replicated storage, failover or corruption recovery.

A second live probe, `timestamp-domain-probe.json`, demonstrates that an explicit
2020 timestamp candidate range still verifies a malformed 2021 record in the same
split and fails HTTP 500. The index has a real `timestamp_field`. The leaf timestamp
rewrite moves the candidate range outside the operator, broadening its verification
domain. `probe-timestamp-domain.py` reproduces this against the retained native
fixtures; it creates its own `composable-timestamp-domain` index and requires that
name to be absent. Numeric candidate success must not be generalized to timestamps.
