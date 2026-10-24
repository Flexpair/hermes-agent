// Fixed Flexpair accent seeds; palette derivation remains Hermes core behavior.
import type { HermesPlugin } from '@hermes/plugin-sdk'
import { host, setAccentOverride } from '@hermes/plugin-sdk'

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
      const previousMode = window.localStorage.getItem(key)
      // Before gateway connection the host paints the boot profile; afterwards
      // it follows the live profile. Preserve assignments for unrelated profiles.
      const bootProfile = desktopWindow.hermesDesktop?.localSkin?.profile
        ?? window.localStorage.getItem('hermes-desktop-active-profile-v1')
        ?? 'default'
      const profiles = [...new Set([bootProfile, host.state.profile.get()].map(profile => profile?.trim() || 'default'))]
        .filter(profile => profile !== 'default')
      const previousModes = profiles.map(profile => [profile, modes[profile]] as const)
      restoreMode = () => {
        try {
          // Restore only our assignments; preserve edits to other profiles.
          const currentModes = readModes()
          for (const [profile, previous] of previousModes) {
            if (previous === undefined) {
              delete currentModes[profile]
            } else {
              currentModes[profile] = previous
            }
          }
          window.localStorage.setItem(profilesKey, JSON.stringify(currentModes))
          if (previousMode === null) {
            window.localStorage.removeItem(key)
          } else {
            window.localStorage.setItem(key, previousMode)
          }
          window.dispatchEvent(new StorageEvent('storage', { key, newValue: previousMode }))
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
    // Disabling or reloading restores the prior mode, theme accent and default zoom.
    ctx.onDispose(() => {
      observer.disconnect()
      setAccentOverride(null)
      restoreMode()
      // Core percentToZoomLevel(0) returns DEFAULT_ZOOM_LEVEL, as Actual Size does.
      // Delegate the default to Hermes rather than hard-coding a percentage.
      setZoom(0)
    })

  }
}

export default plugin
