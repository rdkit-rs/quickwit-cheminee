# Evidence recovery status — 2026-10-16

The [controlled-study report](controlled-study-report.md) and
[archive manifest](controlled-study-archive-manifest.json) were recovered as text
from Library checkpoint `libfile_470ec6694a7c8191abbbc7bcb86622c9`, version 23.
Their historical bodies are preserved. The manifest's validation `passed`, hashes,
member count and original paths describe the prior study's packaging, **not a new
verification**. None of its seven archive parts or retained binary indexes is
present here. Manifest arithmetic was checked; actual part hashes were not.

The full checkpoint was reconstructed locally at
`/workspace/recovery/frozen-tuning-checkpoint.read-reconstruction.json`. It parses,
and its 248,516-byte size matches Library metadata after restoring the final
newline. There is no supplied original-byte hash to prove binary equivalence.
Its locally computed digest and reviewed PR3 source digests are in
[source-audit.json](source-audit.json). The full checkpoint is not included in this
commit; only report and manifest extracts needed for this review are included.

The DSL tar.gz handoff `libfile_5c71df73a9e08191b0930d55a07d44a5` could not be
downloaded. No archive-integrity or recovered-Git verification is claimed.

[Validation scope](validation.json) enumerates performed checks and unrun tests.
[Design review](design-review.md) records an independent Astra max review of PR3.
Neither constitutes campaign readiness. Publication remains on hold.
