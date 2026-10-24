// Fixed Flexpair accent seeds; palette derivation remains Hermes core behavior.
import type { HermesPlugin } from '@hermes/plugin-sdk'
import { host, setAccentOverride } from '@hermes/plugin-sdk'

interface Baseline { global: string | null, profiles: Record<string, unknown>, owners?: string[] }

function readBaseline(baselineKey: string): Baseline | undefined {
  try {
    const saved = JSON.parse(window.localStorage.getItem(baselineKey) ?? 'null')
    if (saved && (saved.global === null || typeof saved.global === 'string')
      && saved.profiles && typeof saved.profiles === 'object' && !Array.isArray(saved.profiles)) {
      return saved
    }
  } catch {
    // A damaged plugin-owned record starts a fresh activation baseline.
  }
}

const plugin: HermesPlugin = {
  id: 'flexpair-color-palette',
  name: 'Flexpair Color Palette',
  description:
    'Start in dark mode with fixed Flexpair accents and 150% desktop zoom. No picker or color commands.',
  defaultEnabled: true,
  register(ctx) {
    // Use the existing Electron bridge, not private core imports or CSS scaling.
    // Zoom is not yet part of the plugin SDK; older hosts keep accent behavior.
    const desktopWindow = window as Window & {
      hermesDesktop?: { localSkin?: { profile?: string }, zoom?: {
        setPercent?: (percent: number) => void
      } }
    }
    const zoom = desktopWindow.hermesDesktop?.zoom
    const setZoom = (percent: number) => {
      try {
        if (typeof zoom?.setPercent === 'function') {
          zoom.setPercent(percent)
        }
      } catch {
        // An incompatible host must not prevent accent initialization or cleanup.
      }
    }
    // Bundled registration runs during module evaluation, before page load.
    // Seed the host's legacy fallback before its asynchronous load-time read;
    // the native setter covers hosts with an existing zoom-state.json as well.
    // Never seed at module scope: disabled bundled plugins are still imported.
    if (typeof zoom?.setPercent === 'function') {
      try {
        window.localStorage.setItem('hermes:desktop:zoomLevel', String(Math.log(1.5) / Math.log(1.2)))
      } catch {
        // Storage can be unavailable; still attempt native zoom and appearance.
      }
    }
    setZoom(150)

    // Each enabled registration starts in dark using the existing preference format.
    // Later manual changes remain available until the next activation.
    let restoreMode = () => {}
    try {
      const key = 'hermes-desktop-mode-v1'
      const profilesKey = 'hermes-desktop-profile-modes-v1'
      const readModes = (): Record<string, unknown> => {
        let saved: unknown
        try {
          saved = JSON.parse(window.localStorage.getItem(profilesKey) ?? '{}')
        } catch {
          // A failed preference read falls back to a fresh profile record.
          saved = {}
        }
        return saved && typeof saved === 'object' && !Array.isArray(saved)
          ? saved as Record<string, unknown> : {}
      }
      const modes = readModes()
      // Socket liveness is not routing authority: a named live route remains
      // known while disconnected, including when this plugin was disabled.
      // Only the initial default placeholder needs a boot-profile hint.
      const bootProfile = new URLSearchParams(window.location.search).get('profile')?.trim()
        || desktopWindow.hermesDesktop?.localSkin?.profile
        || window.localStorage.getItem('hermes-desktop-active-profile-v1')
        || host.state.profile.get()
      const liveProfile = host.state.profile.get().trim()
      const profile = (liveProfile !== 'default' || host.state.gateway.get() === 'open'
        ? liveProfile : bootProfile)?.trim() || 'default'
      const profiles = profile === 'default' ? [] : [profile]
      const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'
      let baseline = readBaseline(baselineKey)
      const currentMode = window.localStorage.getItem(key)
      baseline ??= { global: currentMode, profiles: {} }
      // Dark is our outstanding assignment. A different value is a later
      // manual edit and becomes the next activation's restoration baseline.
      if (currentMode !== 'dark') {
        baseline.global = currentMode
      }
      for (const target of profiles) {
        if (!Object.hasOwn(baseline.profiles, target) || modes[target] !== 'dark') {
          baseline.profiles[target] = modes[target] ?? null
        }
      }
      // Profile ownership survives a restart, without retaining dead renderer tokens.
      const owners = Array.isArray(baseline.owners)
        ? baseline.owners.filter((owner): owner is string => typeof owner === 'string')
        : Object.keys(baseline.profiles)
      baseline.owners = [...new Set([...owners, profile])]
      window.localStorage.setItem(baselineKey, JSON.stringify(baseline))
      // A registration owns only its selected profile, not the origin-wide history.
      const previousModes = profiles.map(target => [target, baseline.profiles[target]] as const)
      restoreMode = () => {
        try {
          // Restore only our assignments; preserve edits to other profiles.
          const currentModes = readModes()
          for (const [profile, previous] of previousModes) {
            if (currentModes[profile] !== 'dark') {
              continue
            }
            if (previous === null) {
              delete currentModes[profile]
            } else {
              currentModes[profile] = previous
            }
          }
          window.localStorage.setItem(profilesKey, JSON.stringify(currentModes))
          // Re-read shared ownership: another registration may have joined later.
          const remaining: Baseline = JSON.parse(window.localStorage.getItem(baselineKey) ?? 'null') ?? baseline
          remaining.owners = (remaining.owners ?? []).filter(owner => owner !== profile)
          for (const target of profiles) {
            delete remaining.profiles[target]
          }
          if (!remaining.owners.length && window.localStorage.getItem(key) === 'dark') {
            if (remaining.global === null) {
              window.localStorage.removeItem(key)
            } else {
              window.localStorage.setItem(key, remaining.global)
            }
          }
          if (remaining.owners.length) {
            window.localStorage.setItem(baselineKey, JSON.stringify(remaining))
          } else {
            window.localStorage.removeItem(baselineKey)
          }
          window.dispatchEvent(new StorageEvent('storage', { key, newValue: window.localStorage.getItem(key) }))
        } catch (error) {
          console.error('[flexpair-color-palette] Could not restore appearance preferences', error)
        }
      }
      for (const profile of profiles) {
        modes[profile] = 'dark'
      }
      window.localStorage.setItem(profilesKey, JSON.stringify(modes))
      window.localStorage.setItem(key, 'dark')
      // Repaint even when the global fallback was already dark: the current
      // profile or in-memory manual selection may still be light.
      window.dispatchEvent(new StorageEvent('storage', { key, newValue: 'dark' }))
    } catch (error) {
      // Surface failed authoritative writes while preserving accent cleanup.
      console.error('[flexpair-color-palette] Could not initialize dark preferences', error)
    }

    const root = document.documentElement
    let lastMode: string | undefined
    // Core publishes the painted mode here, including boot and system changes.
    // Watch it for the plugin's lifetime; no UI contribution is needed.
    const applyInitialAccent = () => {
      const mode = root.dataset.hermesMode
      if ((mode !== 'dark' && mode !== 'light') || mode === lastMode) {
        return
      }
      lastMode = mode
      setAccentOverride(mode === 'dark' ? '#00FFFF' : '#157878')
    }
    const observer = new MutationObserver(applyInitialAccent)
    observer.observe(root, { attributes: true, attributeFilter: ['data-hermes-mode'] })
    applyInitialAccent()
    // Closing releases appearance ownership without changing shared native zoom.
    // Explicit disable/reload also restores the host's default zoom.
    const lifecycleWindow = window
    let disposed = false
    const close = () => dispose(false)
    const dispose = (resetZoom = true) => {
      if (disposed) {
        return
      }
      disposed = true
      lifecycleWindow.removeEventListener('pagehide', close)
      lifecycleWindow.removeEventListener('beforeunload', close)
      observer.disconnect()
      setAccentOverride(null)
      restoreMode()
      if (resetZoom) {
        // Core percentToZoomLevel(0) returns DEFAULT_ZOOM_LEVEL, as Actual Size does.
        // Delegate the default to Hermes rather than hard-coding a percentage.
        setZoom(0)
      }
    }
    lifecycleWindow.addEventListener('pagehide', close)
    lifecycleWindow.addEventListener('beforeunload', close)
    ctx.onDispose(dispose)

  }
}

export default plugin
