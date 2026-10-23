# Independent design review

Independent gpt-6-astra max scoped approval: no blocking defect found for one host
with all writers sharing this journal. Reviewer inspected final tests/result
(16 tests,86 assertions) but did not independently rerun them.

Coverage: publication before/after pointer persistence and stale retries; accepted
writes with lost acknowledgements, saved acknowledgement recovery, disjoint-batch
refusal after uncertainty; competing publishers, uncertain create and interrupted
rollback without another toggle. Shared-file fake peer fixes fork visibility.
Production example unchanged.

Guarantee is local admission and activation control. Direct API writes, another
journal, index deletion/recreation, storage loss and distributed fencing remain
outside it. These tests establish journal/process behavior, not server durability,
wire compatibility or HA.
