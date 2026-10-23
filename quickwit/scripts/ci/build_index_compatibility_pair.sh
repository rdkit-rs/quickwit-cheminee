#!/usr/bin/env bash
# Build the pre-LRU-repair server in the same CI checkout/cache, then restore head.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true ]]; then
  echo 'This build recipe is admitted only on the existing GitHub CI runner' >&2
  exit 1
fi
baseline=c774b166e0bcffa9eadbcda48d4d657d797ca639
repository=$(git rev-parse --show-toplevel)
candidate=$(git rev-parse HEAD)
output=${1:?absolute output directory required}
[[ "$output" == /* && ! -e "$output" ]]
case "$output/" in "$repository/"*) exit 1 ;; esac
git diff --quiet
git diff --cached --quiet
git fetch --no-tags --depth=1 origin "$baseline"
# Capacity refusal, not a claim that four GiB is a sufficient build allowance.
python3 - "$repository" "$(dirname "$output")" "${CARGO_TARGET_DIR:-target}" <<'PY'
import shutil
import sys
for path in sys.argv[1:]:
    if shutil.disk_usage(path).free < 4 * 1024**3:
        raise SystemExit(f'paired rebuild refused: less than four GiB free at {path}')
PY
# BuildInfo reads Git from build.rs. Force that script to run even when Cargo
# restores a cache from another commit; the HTTP probe checks its embedded SHA.
touch quickwit-serve/build.rs
cargo build --locked -p quickwit-cli --features descriptor-v1 --bin quickwit
mkdir -p "$output"
cp target/debug/quickwit "$output/candidate"
printf '%s\n' "$candidate" > "$output/candidate-revision"
printf '%s\n' "$baseline" > "$output/baseline-revision"
restore_head() {
  git -C "$repository" checkout --detach "$candidate"
}
trap restore_head EXIT
git -C "$repository" checkout --detach "$baseline"
touch quickwit-serve/build.rs
cargo build --locked -p quickwit-cli --features descriptor-v1 --bin quickwit
cp target/debug/quickwit "$output/baseline"
restore_head
trap - EXIT
test "$(git rev-parse HEAD)" = "$candidate"
git diff --quiet
sha256sum "$output/baseline" "$output/candidate" > "$output/SHA256SUMS"
