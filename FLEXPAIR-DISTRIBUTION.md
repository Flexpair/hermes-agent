# Minimal Flexpair distribution

`main` stays upstream-shaped. `flexpair.patch` changes `scripts/install.sh` and one narrow desktop activation rule with regression tests:

- Default repository: `Flexpair/hermes-agent` (the upstream override remains supported).
- Install and enable `flexpair-color-palette` at immutable commit `bbff250954d28f992668e227cdb59301befe8717` after the Hermes command is published.
- On reruns, replace this managed plugin with the pinned version, then enable it. Local edits to this plugin are replaced; other plugins are untouched.
- Stop with an error if plugin installation or activation fails.
- Activate the desktop half automatically only when both its package and plugin ID are `flexpair-color-palette`. Explicit desktop disable decisions still win; other unified packages remain opt-in.

No provider, language, platform, update, desktop CSS, theme or core zoom restrictions are included. Accent colors and 150% zoom are implemented by the pinned plugin, not by desktop Core.

## Bootstrap

Download `scripts/flexpair-install.sh` from this repository's `main` and run it with Bash. It selects the lexicographically newest `YYYY-MM-DD-patched` branch from this fork; an explicit `--branch` overrides selection. Existing installer arguments are forwarded. Download and branch-discovery failures stop installation.

Keep the wrapper outside the patch so it is available from `main`. The existing `scripts/install.sh` remains unchanged on `main`; installing directly through that script bypasses automatic dated-branch selection.

## Patch release

Apply `flexpair.patch` to an upstream-synced source branch, verify it, and publish a dated patch branch only after review. Do not publish an unverified higher-date branch: bootstrap selects it immediately.

This change does not replace or deploy any existing dated branch. Old branches still contain the historical patch until a reduced release branch is published. Historical broad-patch documentation is not the scope of this distribution.

## Verification

```sh
scripts/run_tests.sh tests/scripts/install/test_flexpair_install.py
bash -n scripts/flexpair-install.sh scripts/install.sh
git apply --check flexpair.patch
```

Tests execute branch discovery and downloaded-script dispatch with fake network commands and run the real patched installer product stage with isolated command doubles. These do not prove a full fresh Linux/macOS installation or Electron behavior.

The patched desktop loader was also exercised in an isolated real Electron desktop on macOS: no stored desktop plugin decision, automatic 150% zoom, and the dark Flexpair accent `#00FFFF`. The loader regression suite and desktop build passed. This is a local runtime proof, not publication of a dated release or deployment to a cloud desktop.
