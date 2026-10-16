#!/usr/bin/env bash
# Bootstrap the newest dated Flexpair patch branch, without changing upstream's installer.
set -euo pipefail
REPO_URL="https://github.com/Flexpair/hermes-agent.git"
branch=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    case "${args[i]}" in
        --branch|-Branch)
            if ((i+1 >= ${#args[@]})); then
                printf '%s needs a value\n' "${args[i]}" >&2
                exit 2
            fi
            branch="${args[i+1]}"
            ;;
    esac
done
if [ -z "$branch" ]; then
    refs="$(git ls-remote --heads "$REPO_URL" 'refs/heads/*-patched')"
    branch="$(printf '%s\n' "$refs" | cut -f2 | sed -n 's|^refs/heads/\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-patched\)$|\1|p' | LC_ALL=C sort | tail -n 1)"
    [ -n "$branch" ] || { printf 'No dated Flexpair patch branch found\n' >&2; exit 1; }
    args+=(--branch "$branch")
fi
# Allow safe slash-separated branch paths, but never URL traversal or metacharacters.
[[ "$branch" =~ ^[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$ && "$branch" != *..* ]] || { printf 'Invalid branch name\n' >&2; exit 2; }
script="$(mktemp "${TMPDIR:-/tmp}/flexpair-install.XXXXXX")"
trap 'rm -f "$script"' EXIT
curl --fail --silent --show-error --location \
    "https://raw.githubusercontent.com/Flexpair/hermes-agent/$branch/scripts/install.sh" -o "$script"
HERMES_REPO_URL="$REPO_URL" bash "$script" "${args[@]}"
