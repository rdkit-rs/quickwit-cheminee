#!/usr/bin/env bash
set -euo pipefail
: "${QW_CHEMINEE_MODEL_ASSETS:?Set QW_CHEMINEE_MODEL_ASSETS to the destination assets directory}"
model_work_dir=$(mktemp -d)
trap 'rm -rf "$model_work_dir"' EXIT
curl --fail --location --silent --show-error \
  https://cheminee-models.s3.eu-central-1.amazonaws.com/similarity/similarity-0.1.0.tar.gz \
  --output "$model_work_dir/model.tar.gz"
printf '%s  %s\n' 264d7b3af776382dc98e12b1e7c111e76b99a3714ca71acf427bfe63536b26d5 "$model_work_dir/model.tar.gz" | sha256sum --check
tar -xzf "$model_work_dir/model.tar.gz" -C "$model_work_dir"
mkdir -p "$QW_CHEMINEE_MODEL_ASSETS"
cp -a "$model_work_dir/assets/." "$QW_CHEMINEE_MODEL_ASSETS/"
