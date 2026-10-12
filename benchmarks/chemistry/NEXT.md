# Proposed next experiments

These are proposals, not implemented controls or measured speedups.

1. Give chemistry validation a dedicated quota-sized pool or an explicit worker
   setting. The current small-task pool uses `max(QW_NUM_CPUS / 3, 2)`; raising
   the global hint also changes actor pools. Measure 2 versus 4 workers with
   otherwise fixed settings, model-lock wait, queue depth and useful throughput.
2. Compare safe in-process model batching/session scheduling while preserving
   exact cluster assignments and error behavior. TensorFlow was about 40% of
   native indexing CPU, but that fraction is not a guaranteed latency saving.
3. Compare optimized exhaustive exact Tanimoto, current learned routing, and
   direct packed-binary USearch. Audit recall against exhaustive corpus truth.
   Distinguish stable top-k recall from completeness of every match above a
   threshold. Count index construction, serialization, load, retained memory,
   update/deletion and cleanup costs. Existing small compatibility checks do not
   establish real-corpus performance or recall. Direct binary search could
   remove the encoder; latent-vector search would retain it. No TensorFlow
   removal is part of the current configuration study.
4. Benchmark the nested fast JSON descriptor layout against flat descriptors at
   the same code revision, document flags and resources. Experiment 004 supplies
   correctness evidence only; its performance is presently unmeasured.
