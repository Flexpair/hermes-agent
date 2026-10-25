#!/usr/bin/env bash
# Write fixes made on a *-patched branch back into flexpair.patch. Run it ON the patched branch.
# It changes nothing: it prints the new patch and proves base + patch == this branch.
# Usage: flexpair/update-patch.sh [base] > /tmp/flexpair.patch     (base defaults to origin/main)
set -euo pipefail
base="${1:-origin/main}"
branch="$(git branch --show-current)"
[[ "$branch" == *-patched ]] || { echo "run this on a *-patched branch" >&2; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "working tree not clean" >&2; exit 1; }
git merge-base --is-ancestor "$base" HEAD || { echo "$branch is not based on $base; pass the main commit it was created from: flexpair/update-patch.sh \$(git merge-base HEAD origin/main)" >&2; exit 1; }
patch="$(mktemp)"; idx="$(mktemp -u)"; trap 'rm -f "$patch" "$idx"' EXIT
git diff --binary "$base" HEAD | sed "s/$branch/@BRANCH@/g" > "$patch"
GIT_INDEX_FILE="$idx" git read-tree "$base"
sed "s/@BRANCH@/$branch/g" "$patch" | GIT_INDEX_FILE="$idx" git apply --cached
[ "$(GIT_INDEX_FILE="$idx" git write-tree)" = "$(git rev-parse 'HEAD^{tree}')" ] \
  || { echo "patch does not reproduce $branch" >&2; exit 1; }
cat "$patch"
echo "ok: $base + patch == $branch" >&2
