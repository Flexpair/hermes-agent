# Flexpair distribution review

Verified upstream: `20acba0376944d11ee970d6e734afd54bfd8045c`.

The setup branch targets fork `main`. It includes the two directly maintained bundled plugins, the distribution skill, focused tests and an unapplied installer-only `flexpair.patch`. Hermes and Desktop core remain upstream-identical.

The separately prepared `2026-10-18` branch applies this patch. Installers select the Flexpair repository and branch HEAD; repeated installer execution refuses dirty checkouts, different origins, divergent or ahead branches, and commit/channel pins.

## Verification

- Official Vite bundled discovery and lifecycle: 7 tests passed across 3 files, including defaults and saved disable across module reloads.
- Distribution skill: 4 tests passed.
- Desktop typecheck and full build passed.
- Installer patch application check passed on the recorded upstream-based setup revision.

## Review gates

- Native `hermes update` retains upstream behavior and defaults to `main`; use an explicit `--branch 2026-10-18` or rerun the branch installer. No core updater modification is included.
- Palette source deliberately preserves the reference except for `defaultEnabled`; its existing curly/format lint findings remain.
- Native PowerShell execution and an isolated active Electron smoke test remain unverified. Module lifecycle tests are not an active-app smoke test.
- This preparation does not authorize merge, production installation, tags, Terraform or cloud rollout.
