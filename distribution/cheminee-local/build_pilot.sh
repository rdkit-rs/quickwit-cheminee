#!/usr/bin/env bash
# Invoked inside an explicitly admitted disposable builder, never the shared VFS host.
set -euo pipefail
if [ "$#" -ne 1 ] || [ "$1" != --admitted-disposable-builder ]; then
  printf '%s\n' 'usage: build_pilot.sh --admitted-disposable-builder (requires prior resource admission)' >&2
  exit 2
fi
: "${EXPECTED_REVISION:?Set the reviewed full source revision}"
test "$(pwd -P)" = /work/quickwit
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  protobuf-compiler clang libclang-dev lld cmake libssl-dev pkg-config git curl \
  ca-certificates build-essential python3 binutils
test "$(git rev-parse HEAD)" = "$EXPECTED_REVISION"
git diff --exit-code HEAD --
test "$(rustc --version | cut -d ' ' -f 2)" = 1.96.1
timeout 600 bash tantivy-rdkit-mapper/ci/install-rdkit.sh
timeout 600 python3 tantivy-rdkit-mapper/ci/install-tensorflow.py /opt/cheminee-tensorflow
timeout 600 bash tantivy-rdkit-mapper/ci/install-descriptor-model.sh
mkdir -p /work/.pilot/native
dpkg-query -W > /work/.pilot/native/build-packages.txt
rustc --version --verbose > /work/.pilot/native/rust-version.txt
cargo build --locked -p quickwit-cli --features descriptor-v1 --bin quickwit
cargo build --locked -p tantivy-rdkit-mapper --features descriptor-v1 --example descriptor_audit
cargo test --locked -p quickwit-serve --features descriptor-v1 openapi_schema_tests --lib
cargo test --locked -p quickwit-serve --features descriptor-v1 cheminee_api --lib
ldd target/debug/quickwit > /work/.pilot/native/native-linkage.txt
python3 tantivy-rdkit-mapper/ci/descriptor-rest.py --binary target/debug/quickwit \
  --work-dir /work/.pilot/native/descriptor-nested
python3 tantivy-rdkit-mapper/ci/descriptor-rest.py --binary target/debug/quickwit \
  --work-dir /work/.pilot/native/descriptor-flat --layout flat
target/debug/examples/descriptor_audit \
  < /work/sdk/ruby/examples/catalog_native_fixture.ndjson \
  > /work/.pilot/native/catalog-oracle.ndjson
python3 /work/distribution/cheminee-local/prepare_runtime.py \
  --binary target/debug/quickwit --source-root /work --source-commit "$EXPECTED_REVISION" \
  --model-assets "$QW_CHEMINEE_MODEL_ASSETS" --output /work/.pilot/context
