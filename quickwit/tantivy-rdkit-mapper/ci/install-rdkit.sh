#!/usr/bin/env bash
set -euo pipefail
. /etc/os-release
if [ "$ID:$VERSION_ID" != ubuntu:26.04 ]; then
    printf 'Expected Ubuntu 26.04 for the rdkit-rs native package, found %s %s\n' "$ID" "$VERSION_ID" >&2
    exit 1
fi
if [ "$(dpkg --print-architecture)" != amd64 ]; then
    printf 'This installer currently pins the amd64 package hashes.\n' >&2
    exit 1
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates
printf 'deb [arch=amd64 trusted=yes] https://rdkit-rs-debian.s3.eu-central-1.amazonaws.com resolute main\n' > /etc/apt/sources.list.d/rdkit-rs.list
apt-get update
rdkit_download_dir=$(mktemp -d)
trap 'rm -rf "$rdkit_download_dir"' EXIT
cd "$rdkit_download_dir"
apt-get download librdkit-rs202609=2026.09.1+ds1-1~ubuntu26.04 librdkit-rs-dev=2026.09.1+ds1-1~ubuntu26.04 rdkit-rs-data=2026.09.1+ds1-1~ubuntu26.04
printf '%s\n' '47d7dcb895a4983093ccb85407ad0908a6b7c68405147f951a9a72fabf29405d  librdkit-rs-dev_2026.09.1+ds1-1~ubuntu26.04_amd64.deb' '13b43cf87b53bf290a0a5f17c6ce299d8672817d6ff38150d419d16f040b3705  librdkit-rs202609_2026.09.1+ds1-1~ubuntu26.04_amd64.deb' '40a47d0c1ad5f90797db0d833bac9b0dc05c2f5914eec1aaa381c68e341bbe0c  rdkit-rs-data_2026.09.1+ds1-1~ubuntu26.04_all.deb' | sha256sum -c
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ./*.deb
apt-cache policy librdkit-rs-dev librdkit-rs202609 rdkit-rs-data
dpkg-query -W librdkit-rs-dev librdkit-rs202609 rdkit-rs-data
pkg-config --modversion rdkit
