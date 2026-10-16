# Minimal Flexpair distribution

`main` stays upstream-shaped. `flexpair.patch` now changes only `scripts/install.sh`:

- Default repository: `Flexpair/hermes-agent` (the upstream override remains supported).
- Install and enable `flexpair-color-palette` at immutable commit `bbff250954d28f992668e227cdb59301befe8717` after the Hermes command is published.
- Stop with an error if plugin installation or activation fails.

No provider, language, platform, update, desktop CSS, theme or core zoom restrictions are included.

## Bootstrap

Download `scripts/flexpair-install.sh` from this repository's `main` and run it with Bash. It selects the lexicographically newest `YYYY-MM-DD-patched` branch from this fork; an explicit `--branch` overrides selection. Existing installer arguments are forwarded. Download and branch-discovery failures stop installation.

Keep the wrapper outside the patch so it is available from `main`. The existing `scripts/install.sh` remains unchanged on `main`; installing directly through that script bypasses automatic dated-branch selection.

## Patch release

Apply `flexpair.patch` to an upstream-synced source branch, verify it, and publish a dated patch branch only after review. Do not publish an unverified higher-date branch: bootstrap selects it immediately.

This change does not replace or deploy any existing dated branch. Old branches still contain the historical patch until a reduced release branch is published. Historical broad-patch documentation is not the scope of this distribution.

## Verification

```sh
python -m unittest discover -s scripts -p test_flexpair_install.py -v
bash -n scripts/flexpair-install.sh scripts/install.sh
git apply --check flexpair.patch
```

Tests execute branch discovery and downloaded-script dispatch with fake network commands and run the real patched installer product stage with isolated command doubles. These do not prove a full fresh Linux/macOS installation or Electron behavior.
