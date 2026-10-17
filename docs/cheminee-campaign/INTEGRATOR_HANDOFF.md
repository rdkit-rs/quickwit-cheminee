# Integrator and reusable artifacts — 2026-10-16

This thread remains the sole integrator after parallel task creation failed in the
service. No new task was created. Reserve these independent ownership scopes:

- `sdk/ruby` usability/tests, excluding examples and generated code.
- `sdk/ruby/examples` catalog recovery.
- `distribution/cheminee-local` and the resource-measurement harness.

Do not edit those scopes from the integrator while their ownership is reserved.
Only lightweight safe work proceeds at current headroom.

## Admission margin decision

Retain the reviewed 4 GiB growth allowance plus 1 GiB reserve (5 GiB total) and
separate 640 MiB emergency floor. The proposed 2 GiB reserve is provisional;
changing an unvalidated margin alone would not establish capacity. The chosen
1 GiB reserve exceeds the emergency floor by 384 MiB. Neither polling nor that
margin guarantees freedom from exhaustion. Do not reduce allowances to admit a
build; revise them from measured peak growth and recovery requirements. Current
free space is 761,909,248 bytes, so no heavy workspace phase is admitted.

## Exact v5 source and local reuse

Library `libfile_87be743a10bc8191b040da763431f624`, version 5, contains clean source
commit `a90687162c9037e159781b76e97ec43e0bb3a436`, Git bundle, evidence and gem.
Its bundle requires base `6bf1e29cdbf03409287b2f7d0e59a4c19534d8fa`;
the full source archive is also included. Archive SHA256:
`9079f4d6a5d650f6b58acc79c029abbaadfe3731f9623060b2699605a6a776be`.

Rehashed local artifacts:

| Artifact | SHA256 |
| --- | --- |
| `quickwit/target/debug/quickwit` | `5f92e5079f676e7bd6cb21df2e89e3334d8c976abbed69c17d058cb72c7e048d` |
| `/workspace/recovery/campaign-v5-staging/quickwit-cheminee-0.9.1.pre.contract1.gem` | `43208077f9e1907390e306cff34cd901970c964557d4c6119516f4a4319036a9` |
| `/workspace/recovery/compose-runtime-reviewed.tar.gz` | `2e8428db5a377d6bbf391166c16ca8960bb3de97cc0cbdb2ca27d16f96ffaecc` |

The native executable includes the schema/timestamp fixes. The gem and compressed
Compose runtime context retain their earlier server `8009925c` attribution; they
are not new-server release candidates. Do not substitute that older runtime when
testing the new fixes.

Existing `cheminee-native-builder` image ID:
`sha256:abfc41123e9f25f8d4f8815dc625e73e896ab773a12ad79cce2a12c7d82d1866`.
Reuse that running container: all three native fixture readiness endpoints on
127.0.0.1 ports 19480/19490/19500 returned true during this check. PID file:
`/workspace/recovery/composable-native-run1/continuation-fixed-pids.json`.
Readiness is not a fresh correctness or durability test.

The v5 Library archive does **not** contain native executables, Docker images,
large indexes or caches. Fresh tasks sharing this workspace can reuse the local
runtime without rebuilding. A separate machine restoring only v5 cannot assume a
runnable native environment; report missing artifacts instead of rebuilding below
admission or claiming the archive contains them. The Ruby gem is included in v5.
Publication hold remains intact.
