#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
krb5_work_dir=$(mktemp -d)
trap 'rm -rf "$krb5_work_dir"' EXIT

diff - <(printf '%s\n' \
    'name = "krb5-src"' \
    'version = "0.3.4"' \
    'source = "registry+https://github.com/rust-lang/crates.io-index"' \
    'checksum = "a04b2f0dfefd7b54af22d22768dc3ab1ed5e55e6d5ff6af3f619069aa17c0ba4"') \
    < <(grep -F -A3 'name = "krb5-src"' Cargo.lock)

curl --fail --silent --show-error --location \
    https://static.crates.io/crates/krb5-src/krb5-src-0.3.4.crate \
    --output "$krb5_work_dir/krb5-src.crate"
printf '%s  %s\n' a04b2f0dfefd7b54af22d22768dc3ab1ed5e55e6d5ff6af3f619069aa17c0ba4 \
    "$krb5_work_dir/krb5-src.crate" | sha256sum --check
tar --extract --gzip --file "$krb5_work_dir/krb5-src.crate" --directory "$krb5_work_dir"
patch --batch --fuzz=0 --directory "$krb5_work_dir/krb5-src-0.3.4" --strip=1 \
    < "$script_dir/krb5-c23.patch"
cargo --config "paths=[\"$krb5_work_dir/krb5-src-0.3.4\"]" "$@"
