# Process guard evidence

No Cargo or Docker build was launched for these checks. The 11 tiny-process tests
cover admission boundaries, inherited locks, cleanup, durable launch intent,
unknown state review and output-path collisions. Offline preflight passed for the
existing TensorFlow 2.15.1 and checksum-verified Kerberos crate. Admission dependency
revalidation passed inside the existing native builder after the final metadata
selection check was added. This does not prove ABI compatibility or complete Cargo
cache readiness.

Actual workspace admission refused at 762,191,872 free bytes versus the provisional
5,368,709,120-byte requirement. Its log was not created and Cargo was not spawned.
The 640 MiB emergency floor is separate; neither threshold proves sufficient build
capacity. The wrapper test used a harmless Cargo substitute, verified patch and
forwarded arguments, and rejected an invalid cached crate before Cargo.

Independent gpt-6-astra max design review passed the preceding ten-test suite plus
injected low-space and post-launch state-write failure checks with no surviving
process-group members. Implementation review additionally found state/log aliasing
and TensorFlow metadata selection gaps; both were fixed before final review.
The cooperating guard cannot contain descendants that escape its session and close
inherited descriptors. A killed supervisor leaves an inherited duplicate-work lock,
not a surviving disk monitor. Full wrapped workspace validation remains unrun.
