---
name: flexpair-hermes-distribution
description: Use when preparing the Flexpair Hermes fork. Verify gates.
version: 0.2.0
author: Jens Fielenbach, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: devops
    tags: [flexpair, hermes, fork, distribution, desktop-plugins, installer]
    related_skills: []
---

# Flexpair Hermes Distribution Skill

Prepare the Flexpair Hermes fork after an upstream sync with directly maintained in-fork desktop plugins and a small installer-only patch. This workflow grants no permission to publish, install, merge, tag or deploy.

## When to Use

- Sync `Flexpair/hermes-agent` with `NousResearch/hermes-agent`.
- Prepare or inspect an explicitly selected deployment branch.
- Maintain the two in-fork plugins, repair the installer patch after upstream drift, or verify a prepared installation branch.

## Prerequisites

- Load `hermes-agent` and `repository-operations`; read the target revision's root, skill and affected-path `AGENTS.md` files with `read_file`.
- Use `terminal` for Git, Bash, tests and builds; use `search_files`, `read_file`, `write_file` and `patch` for discovery and edits.
- Identify remotes by exact URLs, not local names: fork `https://github.com/Flexpair/hermes-agent.git`, upstream `https://github.com/NousResearch/hermes-agent.git`.
- Maintain plugins directly at `apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx` and `apps/desktop/src/plugins/provider-card-filter/plugin.tsx`.
- Verify official `import.meta.glob` bundled discovery and packaging at the selected upstream revision. Do not add a custom loader or require subtree refs or ancestry.
- Use a clean dedicated worktree. Preserve unrelated work and the user's running Hermes checkout. Credentials stay outside commands, reports and skill files.
- Read [direct-fork setup](references/subtree-setup.md) and [command recipe](references/commands.md); bind parameters to verified evidence before executing.

## How to Run

Ask Hermes to prepare the distribution and state the authorized scope: inspection, local preparation, publication or installation. Use the exact user-selected branch name; if absent, ask rather than infer a date, suffix, tag or pin.

The durable source is `optional-skills/devops/flexpair-hermes-distribution/` in the fork. The active profile's `skills/devops/flexpair-hermes-distribution/` is its runtime mirror. Read the complete directories, preserve legitimate newer rules on either side, update runtime with one atomic `skill_manage` batch, and update repository files byte-identically with file tools. Compare complete file inventories and SHA-256 hashes; never modify another profile implicitly or delete skills.

## Quick Reference

| Location | Contract |
|---|---|
| Fork `main` | Verified upstream basis, directly maintained plugin files, skill/docs and UNAPPLIED `flexpair.patch`; installer/core scripts unchanged. |
| Deployment branch | Exact user-selected name, fresh from verified fork `main`, installer patch applied here only. |
| Plugin reference repository | `Flexpair/hermes-plugins` remains source/provenance reference; do not delete, archive or claim its migration complete. |
| Installed revision | HEAD of the explicitly selected prepared branch through the existing selection mechanism. |

## Procedure

### 1. Establish baseline and authority

Inspect status, branches, linked worktrees and remote URLs. Fetch authorized read-only refs and record exact fork `main` and current selected upstream SHAs. Classify every fork-owned delta and inspect actual installer branch selection. Do not reuse old feature/PR ancestry as a shortcut. The verified upstream for the current preparation is `548091836760a67e331b8f5643be8e5c08fae1e6`; reverify current upstream for later runs rather than treating this historical value as a pin.

Completion: exact baseline, authorized scope and explicit allowed/protected paths are recorded.

### 2. Prepare the upstream-sync/setup review

Prepare a separate review branch retaining the in-fork plugins, this skill, relevant docs and unapplied patch. Resolve conflicts preserving both intents; do not reset away fork-owned files. Prove installer scripts and protected Hermes/Desktop core unchanged relative to the selected upstream. Run tests for actual upstream changes. A setup PR targets fork `main`; it must not contain applied installer changes. Updating or merging `main` requires separate approval and exact remote read-back.

Completion: the verified fork baseline includes the intended direct-fork assets without applied installer behavior.

### 3. Select the deployment branch

Use the exact branch chosen by the user, without deriving it from `%cs`, today's date or an old naming convention. The current user choice is exactly `2026-10-18`, not `2026-10-18-patched`. This is context, not permission to select the same name automatically on later runs. Show the base SHA and exact name; obtain authorization if missing. Check local and remote existence. An existing branch requires inspection and a decision, not reset, silent reuse or suffixing.

Create the authorized branch in a separate worktree from verified fork `main`. Completion: base ancestry and exact branch identity are proven; unrelated/live checkouts remain untouched.

### 4. Apply the installer-only patch

Read the entire `flexpair.patch` and inventory targets against the explicit installer/focused-test allowlist; plugin source stays outside it. Run `git apply --check`, then `git apply --index`, review staged paths and test error propagation. Commit explicit paths only with Git-write authority.

On conflict, inspect the old patch as a behavioral reference, rebuild the smallest installer-only patch against the verified new base and exercise it in a disposable checkout. Do not reuse historical ancestry, skip hunks or leave rejects. Updating the stored unapplied patch for `main` is a separate reviewed change; never apply its contents there. The patch is a development/sync tool, not a runtime plugin loader.

Completion: expected installer behavior, clean application and nonzero failure exits are tested; no plugin bytes or core changes enter the patch.

### 5. Maintain plugins directly in the fork

Edit the two named `plugin.tsx` files directly using supported plugin APIs. Preserve identities, licenses, original provenance and relevant behavioral rules. Record any reference revision/transformation from `Flexpair/hermes-plugins` without making that repository, an export ref, or subtree metadata a prerequisite. Review plugin changes through fork `main` so future deployment branches inherit them; no mandatory source-first publication or subtree pull is required.

Both manifests use `defaultEnabled: true`; saved explicit `false` must remain honored through restart and update. Use official `import.meta.glob` discovery without modifying the bundled loader or other protected core paths. An unsupported API/discovery gap is a scope conflict, not permission to patch core.

Completion: maintained source, reviewed provenance and real loader/lifecycle checks agree; no custom downloads or runtime patch-loading path is introduced.

### 6. Verify the combined distribution

Compare all changed paths with the recorded upstream SHA and explicit allowlist: installer/update behavior on the deployment branch, the two plugin directories, focused tests, independently named relevant CI and concise docs/skill. Prove protected Hermes/Desktop core blobs unchanged.

Run real fresh-profile defaults and saved-disable persistence tests through the official loader. Trace packaging and run the relevant desktop/plugin build. Test selected-branch HEAD installation/update behavior in isolation, including nonzero installer failure exits and no plugin downloads at install time. Repeat relevant checks in a fresh disposable clone. Keep CI focused on actual changes; upstream sync needs its actual scope tested. Missing mandatory checks are blockers, not passing results. Source-reading assertions and registration mocks do not prove real loader or live Desktop behavior.

Run `scripts/run_tests.sh tests/skills/test_flexpair_hermes_distribution_skill.py -q` for this skill. Its offline fixtures validate the command workflow, not product loader/build coverage.

Completion: each acceptance check has real output; distinguish source, build, isolated runtime and active-app verification rather than implying one proves another.

### 7. Publish or hand off within scope

Review the allowlisted diff and commit explicit paths. Publication requires its own authorization: push only to the Flexpair fork and read back the exact target SHA. Setup/skill/docs/unapplied-patch review targeting `main` stays separate from the deployment branch. Never open a PR that merges applied installer changes into `main` by default.

Install only HEAD of the explicitly selected branch through the verified existing selection/script-fetch path. Do not introduce automatic branch selection, tag/commit pinning or a merge-back policy. Installation, merge, tags, history rewriting, Terraform and cloud rollout remain separately gated.

Completion: report exact branch/upstream/plugin provenance, complete source/runtime file-hash manifest, test commands/results and remaining approvals. Claim publication only after remote read-back and installation only after runtime verification.

## Pitfalls

- Legacy subtree reference filenames are compatibility links, not requirements for subtree ancestry.
- Do not delete/archive `Flexpair/hermes-plugins` or claim its migration complete.
- A provenance SHA is not an installation pin; installation tracks selected branch HEAD.
- Both defaults being true must never overwrite a persisted user disable.
- Bash templates are POSIX examples; native Windows needs a separately verified path.

## Verification

- Current upstream and all fork deltas are classified; protected core remains unchanged.
- `main` holds direct plugin source and an unapplied installer-only patch; deployment application remains separate.
- Exact user branch choice is preserved without inferred dates, suffixes, pins or automatic selection.
- Official discovery, defaults, persistent disablement, builds, installer/update and fresh-clone portability have real results.
- Complete runtime/source inventories and SHA-256 hashes match; canonical skill tests pass.
- Handoff distinguishes local preparation, publication and actual installation with approvals still explicit.
