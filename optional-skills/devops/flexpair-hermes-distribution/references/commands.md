# Preparation command recipe

Parameterized POSIX commands for `terminal`, not an unattended release script. Run phases separately and review output; this recipe grants no write/publication/installation authority.

## Bind parameters

Resolve `FORK_REMOTE` and `UPSTREAM_REMOTE` by exact verified URLs. Set `BASE_MAIN` to verified fork `main`, `UPSTREAM_SHA` to reviewed current upstream, `PATCH_BRANCH` to the exact user choice and `WORKTREE` to a new managed scratch or approved durable path. Preserve identifiers exactly, quote parameters and reject missing variables. No plugin export ref, prefix or history mode is required.

## Read-only inspection

```bash
set -euo pipefail
git status --short --branch
git remote -v
git worktree list
git log -1 --format='%H %cI %s' "${BASE_MAIN:?}"
git diff --name-status "${UPSTREAM_SHA:?}" "$BASE_MAIN"
git show-ref --verify --quiet "refs/heads/${PATCH_BRANCH:?}" || test "$?" -eq 1
git ls-remote --heads "${FORK_REMOTE:?}" "refs/heads/$PATCH_BRANCH"
```

Check both outputs for existing branches; stop for a decision if present. Use the branch name the user chose; `flexpair/new-branch.sh DATE` yields `DATE-patched`. Record protected paths and verify the actual installer selection contract before preparing anything.

## Authorized branch creation

```bash
set -euo pipefail
git worktree add -b "${PATCH_BRANCH:?}" "${WORKTREE:?}" "${BASE_MAIN:?}"
```

Use that worktree as `terminal` workdir. Read the complete patch with `read_file`, inventory targets and review its targets before application.

## Deployment-only application

Preferred: `flexpair/new-branch.sh DATE` (creates `DATE-patched` from `origin/main`, renders and applies the patch, commits). Manual equivalent, run in the new worktree:

```bash
set -euo pipefail
rendered="$(mktemp)"
sed "s/@BRANCH@/${PATCH_BRANCH:?}/g" flexpair.patch > "$rendered"
git apply --check "$rendered"
git apply --index "$rendered"
git diff --cached --check
git diff --cached --name-status
```

`flexpair.patch` is a template: `@BRANCH@` must become the deployment branch name. Applying it unrendered yields an installer with `BRANCH="@BRANCH@"`.

Run real installer/error-exit tests and commit explicit approved paths only. On conflict, resolve on the deployment branch, commit, then `flexpair/update-patch.sh > /tmp/flexpair.patch` and store that file as `flexpair.patch` on `main` (see `FLEXPAIR-DISTRIBUTION.md`). Never apply the patch on `main` itself.

## Direct plugin maintenance and checks

Use `read_file`/`patch` to maintain `apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx` and `apps/desktop/src/plugins/provider-card-filter/plugin.tsx` directly. Keep `defaultEnabled: true` for both and honor persisted `false` through official `import.meta.glob` discovery. Preserve the reference repository and provenance; no subtree add/pull or source-first publication is required.

```bash
set -euo pipefail
git diff --check
git diff --name-status "${UPSTREAM_SHA:?}" HEAD
git diff --exit-code "$UPSTREAM_SHA" HEAD -- "${PROTECTED_PATH:?}"
scripts/run_tests.sh tests/skills/test_flexpair_hermes_distribution_skill.py -q
```

Repeat the protected-path comparison for every exact protected path. Recover loader/default-disable, installer and build commands from the selected revision's manifests/tests, then execute them and repeat relevant checks in a fresh clone. Skill fixture tests do not establish product lifecycle/build verification.

## Optional publication and installation

When authorized, push to the verified fork remote only and read back the exact target:

```bash
set -euo pipefail
git push "${FORK_REMOTE:?}" "HEAD:refs/heads/${PATCH_BRANCH:?}"
git ls-remote "$FORK_REMOTE" "refs/heads/$PATCH_BRANCH"
git rev-parse HEAD
```

Compare remote SHA with local HEAD. Setup PRs target fork `main` without applied installer diffs; deployment preparation remains separate. Installation needs independent approval and the actual existing selected-branch installer path. Verify branch HEAD checkout/update, nonzero failures and no plugin downloads; do not guess a script URL, autoselect a dated branch or replace HEAD with a tag/commit pin.
