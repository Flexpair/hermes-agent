# Direct-fork plugin setup

This filename remains for compatibility with existing links. It describes direct in-fork maintenance, not subtree import, export refs or required ancestry. Setup work grants no release/install/publication authority.

## Commit the setup contract

Use `read_file` and `search_files` to inspect the selected upstream's official `import.meta.glob` bundled-plugin discovery, manifests, APIs and package assembly. Read affected `AGENTS.md` files. Record in reviewed fork documentation:

| Required field | Evidence |
|---|---|
| Upstream basis | Verified current full upstream commit. |
| Fork-owned source | `apps/desktop/src/plugins/flexpair-color-palette/plugin.tsx` and `apps/desktop/src/plugins/provider-card-filter/plugin.tsx`. |
| Reference provenance | `https://github.com/Flexpair/hermes-plugins.git`, reviewed immutable revision, licenses and any transformation when reused. |
| Discovery/lifecycle | Official bundled discovery, both `defaultEnabled: true`, persisted `false` honored. |
| Allowed/protected paths | Plugin directories, installer-only patch, focused tests/CI/docs; core/loader unchanged. |
| Verification commands | Real loader/default-disable tests, installer/error-exit checks, build and fresh-clone verification. |

Do not invent revisions, APIs or test results. `Flexpair/hermes-plugins` remains source/provenance reference; do not delete, archive or claim its migration complete. Neither availability of a published export ref nor subtree metadata gates direct-fork maintenance.

## Initial setup and review

1. Create a separate setup review branch/worktree from verified current upstream/fork basis, preserving legitimate fork assets and unrelated/live checkouts.
2. Maintain the two plugin files directly using supported APIs. Preserve identities, license and original provenance. Leave installer/core scripts unchanged on `main`.
3. Keep `flexpair.patch` stored UNAPPLIED on `main`; it is an installer-only development/sync artifact, never a runtime plugin loader.
4. Exercise real discovery, fresh-profile activation, saved-disable persistence, packaging/build and protected-core comparisons. Unsupported discovery/API requirements are scope conflicts, not authorization for core changes.
5. Commit explicit setup/plugin/skill/docs/unapplied-patch paths for a separate fork `main` PR. No applied installer diff belongs in that PR. Publication and merge each need their own approval and exact remote read-back.
6. Prepare the exact user-selected deployment branch from verified fork `main` in a separate worktree; apply/test the installer patch there. Do not derive dates, append suffixes, autoselect branches or add tag/commit pins. Installation tracks that branch's HEAD and requires separate authorization.

## Later updates

Review plugin changes directly through fork `main` so new deployment branches inherit them. Reference-source comparison can inform provenance, but no mandatory source-first release or subtree pull is required. Repair installer conflicts using the old patch as behavioral reference; rebuild the smallest installer-only patch against the new upstream and test it in a disposable checkout. Store reviewed patch updates unapplied on `main`, with deployment application separate.

## Skill source and mirror

The durable source is `optional-skills/devops/flexpair-hermes-distribution/`; the active profile's `skills/devops/flexpair-hermes-distribution/` is the runtime mirror. Read every file on both sides and prior tracked source when reconciling; preserve legitimate newer rules, never delete skills or modify another profile implicitly. Use one atomic `skill_manage` batch for runtime updates and file tools for byte-identical repository files. Compare complete relative-file inventories and SHA-256 hashes, run `scripts/run_tests.sh tests/skills/test_flexpair_hermes_distribution_skill.py -q`, and report the exact commit, manifest and real results. Offline command fixtures are not a substitute for loader/build/runtime checks.
