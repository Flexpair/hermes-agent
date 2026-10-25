#!/usr/bin/env bash
# Create a deployment branch from synced main and apply flexpair.patch.
# Run from the repository root.
# Usage: flexpair/new-branch.sh 2026-10-27 [base]      (base defaults to origin/main)
#
# Everything sits in main() and the script ends with `exit`: bash has then read the whole
# file before `git switch` can replace it on disk (the base may carry a newer copy).
main() {
  set -euo pipefail
  local name="${1:?date, e.g. 2026-10-27}-patched"
  local base="${2:-origin/main}"
  git diff --quiet && git diff --cached --quiet || { echo "working tree not clean" >&2; return 1; }
  [ "$base" != origin/main ] || git fetch -q origin main
  git switch -c "$name" "$base"
  render() { sed "s/@BRANCH@/$name/g" flexpair.patch; }
  if ! render | git apply --index --whitespace=nowarn 2>/dev/null; then
    echo "flexpair.patch does not apply cleanly; retrying as 3-way merge ..." >&2
    if ! render | git apply --3way --whitespace=nowarn; then
      echo "" >&2
      echo "Conflicts remain in the files listed above (look for <<<<<<< markers)." >&2
      echo "Resolve them, then: git add -A && git commit --no-verify -m 'chore: apply flexpair.patch for $name'" >&2
      echo "Then run flexpair/update-patch.sh so that main's flexpair.patch carries the fix." >&2
      echo "To give up: git reset --hard && git switch - && git branch -D $name" >&2
      return 1
    fi
  fi
  git commit -q --no-verify -m "chore: apply flexpair.patch for $name"
  echo "created $name from $base"
}
main "$@"; exit $?
