# Flexpair distribution review

Verified upstream: `20acba0376944d11ee970d6e734afd54bfd8045c`.

The setup branch targets fork `main`. It includes the two directly maintained bundled plugins, the distribution skill, focused tests and an unapplied installer-only `flexpair.patch`. Hermes and Desktop core remain upstream-identical.

The separately prepared `2026-10-18` branch applies this patch. Installers select the Flexpair repository and branch HEAD; repeated installer execution refuses dirty checkouts, different origins, divergent or ahead branches, and commit/channel pins.

## Verification

- Official Vite bundled discovery and lifecycle: 7 tests passed across 3 files, including defaults and saved disable across module reloads.
- Distribution skill: 4 tests passed.
- Desktop typecheck and full build passed.
- Installer patch application check passed on the recorded upstream-based setup revision.

## Fork CI proof reuse

Fork pull requests admit only the enumerated Flexpair delta in `scripts/ci/fork_scope_paths.json`, relative to the immutable upstream anchor above. Unknown core, dependency, catalog-entry or runtime-installer changes fail admission; missing ancestry, unavailable API evidence or failed upstream consumers also fail closed. Adding a reviewed path requires code review, not a label override.

The gate revalidates successful upstream push run [39177780870](https://github.com/NousResearch/hermes-agent/actions/runs/39177780870) and its individual Linux/macOS/Windows, bootstrap, Rust, remote-backend and workspace-check consumers. Unchanged core trees reuse that proof; changed Desktop plugins still run focused integration, typecheck, lint and build locally. Skipped upstream E2E is not passing proof. The Actions summary distinguishes reused proof from executed fork checks.

Installer patch (9), skill (4), catalog synchronization (6), bundled plugin and Radio integration tests remain selected. Catalog pinned-source validation, supply-chain review, contributor attribution, docs regeneration/freshness/build and existing repository hygiene gates remain independent. The aggregate requires the selected fork job to succeed. Push, dispatch and release retain the full upstream routing policy. This is PR admission, not authorization to deploy or install.

## Review gates

- Native `hermes update` retains upstream behavior and defaults to `main`; use an explicit `--branch 2026-10-18` or rerun the branch installer. No core updater modification is included.
- Palette source deliberately preserves the reference except for `defaultEnabled`; its existing curly/format lint findings remain.
- Native PowerShell execution and an isolated active Electron smoke test remain unverified. Module lifecycle tests are not an active-app smoke test.
- This preparation does not authorize merge, production installation, tags, Terraform or cloud rollout.
