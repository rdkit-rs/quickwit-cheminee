# Real Cheminee 100k / kind / SeaweedFS acceptance

AI-assisted implementation by OpenAI Codex. **Prepared harness, not a passing
acceptance claim.** No merge, registry/package publication or production access.

This separate workflow consumes the exact successful pilot run in `candidate.json`.
It never compiles a native runtime or dispatches another pilot build. The accepted
artifact must pass the existing image/gem/schema/restore provenance validators;
failure-only diagnostics are never admitted as runtime artifacts. Update the pinned
full commit and run together only after a reviewed pilot handoff. A bounded 20-minute
wait accommodates an already-running pilot; a missing/failed artifact fails closed.

## Execution and evidence

Open a PR changing this directory or its workflow to trigger the standard
`ubuntu-24.04` job. Workflow dispatch also works once GitHub recognizes the workflow
on the repository default branch. Repository token permissions are only contents
and actions read. The automatic token is scoped to the job and never persisted;
there are no repository secrets or external credentials. S3 credentials are fixed
throwaway strings for internal disposable services. One acceptance job runs at a
time, maximum 120 minutes, with seven-day evidence retention. The runtime phase is
bounded to 90 minutes; no larger paid runner or host/security fallback exists.

Provisional admission is 20 GiB free persistent storage and 10 GiB RAM. This includes
kind/containerd duplication, images, corpus, active/staging/rollback generations,
WAL/cache, backup, separate restore and 4 GiB reserve. These are experimental
allowances, not measured sizing requirements. A smaller standard runner reports
the capacity blocker without deleting its assets. Native pod memory is capped at
4 GiB and two CPUs, SeaweedFS at 768 MiB/one CPU each, and indexing heap at 128 MiB.
The original object store is stopped before the separate restore store is used.

The workflow installs checksum-pinned kind 0.30.0 and uses an immutable Kubernetes
1.34.0 node image and SeaweedFS 3.85 amd64 image digest. Only loopback API/forwarded
ports are exposed; SeaweedFS has ClusterIP services. The existing saved Codex host
is not used, changed, or retried. Kind's normal hosted-runner privileges are needed;
no `/dev/kmsg` workaround or firewall disabling is included.

## Gates

- Reproduce the public MOSES 100k corpus from the pinned molsets wheel using the
  source preparer, requiring an identical manifest. Retain provenance and license.
- Submit raw SMILES through the artifact-installed Ruby SDK and exact native
  importer. Reject caller-derived fields through that importer contract. Audit every
  original record and native field via bounded partitions, never top-k samples.
- Require rejection/quarantine for incomplete snapshots, premature publication,
  invalid SMILES, mixed acceptance, acknowledgement loss **after real server
  acceptance**, duplicate-and-omitted records with matching counts, and stale input.
- Independently reproduce preparation and Morgan/Pattern fingerprints for every
  exported record with RDKit 2025.09.3. Native uses 2026.09.1: differences fail and
  must be investigated, not normalized away. Retain raw/prepared unique counts,
  scaffolds, complete row-hash lists, exact query expected/actual results and times.
- Check curated native goldens and graph/similarity semantics plus chirality,
  isotopes and salts. Audit complete identity, substructure and similarity result
  sets for three diverse corpus queries, supplier filters and an absent supplier.
  Queries exceeding the result cap fail rather than silently accepting truncation.
- Apply full refresh with update/removal/addition and retain the rollback generation.
  Cleanly TERM/exit-check the runtime, start a new pod on retained data and re-audit.
- Quiesce the source, SHA256 every actual S3 object and local data/journal file,
  verify a distinct empty destination, restore to another SeaweedFS endpoint with
  source stopped, compare every object/file, and re-audit without reimport.
- Roll back the restored facade journal and verify initial full-source equality and
  unchanged sequence high-water marks. Run bounded two-client reads, twelve requests
  per oracle phase, with exact-result checks and per-request timing.

Failures retain logs/manifests, exact versions, image identities, phase receipts,
S3/file inventories and resource samples under `.e2e/evidence`. Full corpus bytes
are reproducible from the pinned input; runtime data remains only on the disposable
runner. No pass is inferred from process startup or from a skipped prerequisite.

## Limits

Clean restart/offline backup does not prove crash/WAL durability, online backup,
multi-node HA or production sizing. Bounded read load is not a throughput benchmark
or a concurrent-writer guarantee. Native descriptor shape is audited in all rows;
independent descriptor-value truth is limited to the retained curated golden cases.
The single-owner importer journal is not a distributed alias or fencing service.
Existing dependency security findings remain a release hold.

Local checks: `python3 -m unittest discover -s distribution/cheminee-e2e -p 'test_*.py' -v`,
Python compilation, Ruby syntax in the pinned CI Ruby, and YAML validation.
`make fmt` was invoked locally; Rust formatting was unavailable because this fresh
executor has no rustup/nightly. No Rust source is changed.
