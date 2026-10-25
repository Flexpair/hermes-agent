# Flexpair distribution

`main` is upstream (`NousResearch/hermes-agent`) plus Flexpair-only **new** files. It never edits an upstream file, so syncing it with upstream cannot conflict.

## Layout

| Where | What |
|---|---|
| plain files in `main` | bundled desktop plugins `flexpair-color-palette` and `provider-card-filter` (found by the Vite glob in `apps/desktop/src/contrib/plugins.ts`) with their tests, the distribution skill and its docs page, contributor mappings, the installer test, `flexpair/new-branch.sh`, `flexpair/update-patch.sh` |
| `flexpair.patch` | everything that edits an existing upstream file, or is only green together with such an edit: installer defaults (`scripts/install.sh`, `scripts/install.ps1`, branch name template `@BRANCH@`), three core repairs (owning-profile deletion hooks, durable worker CAS rejection, MCP context-cost cache) with their tests, the Radio test baseline for default-enabled plugins, two docs index lines |

## Daily routine

1. Sync `main` with upstream (GitHub *Sync fork*).
2. `flexpair/new-branch.sh 2026-10-27` creates `2026-10-27-patched` from `origin/main` and applies `flexpair.patch`.
3. A conflict can only occur in files named in `flexpair.patch`. Resolve it there, then `git add -A && git commit --no-verify`. To keep the fix, run `flexpair/update-patch.sh > /tmp/flexpair.patch` on the patched branch, copy that file over `flexpair.patch` on `main` and commit it there; otherwise the next branch fails the same way.

## Rules

- New Flexpair code is a new file in `main`.
- Touching an upstream file means a hunk in `flexpair.patch`, never a commit on `main`.
- `main` alone is not the tested artifact: the Radio test and the skill docs test need the patch lines. The patched branch is.
- Fork CI (runner swaps, `fork_scope` gate, `fork-delta` workflow) is not carried. The gate compares against one fixed upstream commit and fails after every sync.
- Native `hermes update` follows upstream `main`; install from the patched branch with the branch installer.
