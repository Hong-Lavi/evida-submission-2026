#!/usr/bin/env bash
set -euo pipefail

# Fetch original implementations into a new local directory. This script is not run by archive verification.
if [[ $# -ne 1 ]]; then
  echo 'Usage: bash fetch_authors.sh NEW_EMPTY_DIRECTORY' >&2
  exit 2
fi
source_dir=$1
if [[ -e "$source_dir" ]]; then
  echo 'Destination already exists; choose a new empty directory.' >&2
  exit 2
fi
mkdir -p "$source_dir"
git clone https://github.com/bioasp/caspo.git "$source_dir/caspo"
git -C "$source_dir/caspo" checkout 45b41124ab933996687f1e0581a4f15b32e7806f
git clone https://github.com/saezlab/corneto.git "$source_dir/corneto"
git -C "$source_dir/corneto" checkout d9f6d238d6c41cc20ecc0b4a17d105cbf209b360
printf 'caspo %s\n' "$(git -C "$source_dir/caspo" rev-parse HEAD)"
printf 'corneto %s\n' "$(git -C "$source_dir/corneto" rev-parse HEAD)"
