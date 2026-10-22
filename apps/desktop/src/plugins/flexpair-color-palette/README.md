# flexpair-color-palette

Reference: https://github.com/Flexpair/hermes-plugins.git at `78640444605766af176c202854d66c2d1da64d64`, `flexpair-color-palette/src/plugin.tsx`. Upstream host basis: `3752497cc4d214023f4736559a5f0e58621af9ff`. License copied unchanged from the reference plugin directory. Maintained directly in the Flexpair fork.

Only `defaultEnabled` changed to `true`. Fixed accents, once-on-enable 150% zoom and host-default reset on disposal remain intact. Optional existing Electron zoom bridge is not a plugin SDK API.

Official Vite bundled discovery enables fresh defaults; stored explicit disablement takes precedence across restarts and app updates.
