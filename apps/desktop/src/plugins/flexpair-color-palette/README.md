# flexpair-color-palette

Reference: https://github.com/Flexpair/hermes-plugins.git at `78640444605766af176c202854d66c2d1da64d64`, `flexpair-color-palette/src/plugin.tsx`. Upstream host basis: `3752497cc4d214023f4736559a5f0e58621af9ff`. License copied unchanged from the reference plugin directory. Maintained directly in the Flexpair fork.

Enabled by default. Every enabled registration sets the appearance preference to dark, including a previously saved light preference. Synchronous bundled registration seeds the host's legacy zoom fallback and requests native 150% zoom before page load. Later manual mode and zoom changes remain available until the next activation or app restart; no timer, load listener or zoom notification reasserts the plugin defaults.

Fixed accents follow the painted mode. Disposal restores the mode preferences captured before activation, clears the accent override and resets zoom to the host default. Changes to unrelated profiles are preserved. The optional existing Electron zoom bridge is not a plugin SDK API; older hosts without it retain appearance behavior. SDK, theme implementation, Electron and plugin loading remain unchanged. These defaults are applied during initialization, not guaranteed before the first native window paint. Unavailable storage or native zoom cannot guarantee 150%.

Official Vite bundled discovery enables fresh defaults; stored explicit disablement takes precedence across restarts and app updates.
