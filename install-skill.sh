#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
source_dir="$repo_root/skills/vision-power"
codex_home="${CODEX_HOME:-$HOME/.codex}"
target_root="$codex_home/skills"

mkdir -p "$target_root"
cp -R "$source_dir" "$target_root/"

echo "Installed skill to $target_root/vision-power"
echo "Restart Codex if the skill list is already loaded."
