# Configuration study harness

This harness runs the **unchanged measured flat-schema binary**. It does not build
or alter the service. Each run creates a fresh directory, checks for competing
engines/builds, and takes an exclusive lock. Zombie processes are excluded from
the competing-work check. No request retry is performed. A failed or overlapping
run must be retained and excluded explicitly, not silently overwritten.

Prepare a fresh absolute `STUDY_ROOT` with `bin/quickwit-control`, the verified
model/library environment and `data/flat-index.json` copied as
`data/quickwit-index.json`. Use the exact revision and binary hash in experiment
003. A CPU-instrumented run additionally needs the original separately built
`quickwit-instrumented` and instrumentation library; these large overlays/binaries
are not supplied by this documentation PR. Uninstrumented runs need no overlay.

Extract the verified molsets 0.3.1 wheel into `$STUDY_ROOT/data/molsets`, producing
`molsets/moses/dataset/data/{train,test,test_scaffolds}.csv.gz`. Then:

```sh
export STUDY_ROOT=/absolute/path/to/new-study
export STUDY_OUTPUT=/absolute/path/to/metrics-output
mkdir -p "$STUDY_ROOT/runs" "$STUDY_OUTPUT"
python3 sample_corpus.py
cp flat-index.json "$STUDY_ROOT/data/quickwit-index.json"
python3 run_case.py quickwit --tag knobs-base-1 --size 100000 \
  --batch 200 --concurrency 1 --cpu-hint 4 --commit-seconds 30 \
  --boot-idle 30 --lifecycle-seconds 60
python3 run_case.py quickwit --tag knobs-hint12-1 --size 100000 \
  --batch 200 --concurrency 1 --cpu-hint 12 --commit-seconds 30 \
  --boot-idle 30 --lifecycle-seconds 60
python3 summarize.py
```

Run commands sequentially inside the same four-core/14 GiB container. The second
command is an example diagnostic, not a recommendation or preselected winner.
Effective environment/quota/affinity, node/index config, requests, process samples,
phase boundaries, metrics and file/split inventories are saved per run. The CPU
hint changes several internal pools; the kernel quota remains four. Scheduling
capacity stays 4000m, merge concurrency 2, uploads 12, main Tokio threads 2.

`audit_stored.py TAG` restarts metastore/searcher roles and compares all stored
SMILES, Morgan, Pattern and metadata against `audits/native-100k.ndjson`. Generate
that comparison-only oracle with the pinned native `descriptor_audit` example,
and independently compare it with Cheminee preparation before relying on it.
This oracle is never an ingestion input. Query oracles are separate from readback.

Screen defaults use a bounded shutdown wait, then may SIGKILL a draining service;
`forced_shutdown` and exit code are retained. Restart readback follows termination.
The searchable timing interval precedes shutdown. Long lifecycle runs wait up to
330 seconds for normal shutdown. Do not call a 60-second observation fully cleaned
storage: use at least 2580 seconds to observe the normal grace plus GC sweep,
and record actual split deletion. This is not a power-loss durability test.

`summarize.py` reports nonoverlapping approximately ten-second CPU bins and
phase totals; samples are once per second. JSON counters are actual process CPU,
not requested thread counts. It preserves short/long lifecycle distinctions and
shared process memory. It does not infer owned allocations or assign unmeasured
substeps from RSS. Validate every audit and status before using its headline.

## Capacity and evidence export

The final harness adds a pre-launch disk check outside timed intervals. It budgets
512 MiB of additional space for each 100k run, including the temporary coexistence
of raw and compressed audits, and preserves a 2 GiB filesystem reserve. The budget
comes from measured retained runs of at most approximately 230 MiB plus about
100 MiB of audit overlap. Larger samples require a new capacity estimate. A failed
check stops before launching an engine; it does not shrink or overwrite the run.
Builds require a separate preflight. Preserve source data and original results.

After the complete sequential experiment and audits finish:

```sh
export EVIDENCE_OUTPUT=/absolute/path/to/sanitized-evidence
mkdir -p "$EVIDENCE_OUTPUT"
python3 summarize.py
python3 enrich.py
python3 public_metrics.py
python3 public_traces.py
```

`enrich.py` reads resource and stage counters, request boundaries, split/footer
metadata and file inventories. It retains same-window CPU reconciliation, actual
lifecycle transitions and internal segment counts. Run it where the retained
index files are readable. `public_metrics.py` validates reconciliation and rejects
accidental local paths or private identifiers. `public_traces.py` exports a
whitelist of counter fields, request counts and split transitions; it omits process
IDs, memory addresses, local paths, service logs and molecule payloads. Its archive
manifest identifies excluded attempts and links every member's hash to its retained
original source hash. The archive is reopened and checked after creation.

These exports require all twelve planned full runs. They do not turn correctness
probe latencies into a query-performance study. `stage-names.json` describes the
original measurement overlay; publishing that map does not supply the separately
built overlay binary or claim stage-owned memory measurements.
