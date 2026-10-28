// Fixed Flexpair accent seeds; palette derivation remains Hermes core behavior.
import type { HermesPlugin } from '@hermes/plugin-sdk'
import { host, randomUuid, setAccentOverride } from '@hermes/plugin-sdk'

interface Baseline { global: string | null, profiles: Record<string, unknown>, owners?: Record<string, string>, generations?: Record<string, string> }
const legacyOwnerPrefix = 'legacy:'

function registrationOwner(window: Window, profile: string): string {
  const key = 'hermes-desktop-plugin-flexpair-color-palette-window-v1'
  let windowId = window.sessionStorage.getItem(key)

  if (!windowId) {
    windowId = randomUuid()
    window.sessionStorage.setItem(key, windowId)
  }

  // Session storage survives renderer reload/crash, but is separate per window.
  return `${windowId}:${profile}`
}

function readBaseline(window: Window, baselineKey: string): Baseline | undefined {
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

// One discovery per activation, not a recurring lease. Suspended peers may miss it.
const presenceScope = 'flexpair-color-palette:presence:v1'
const presenceTimeoutMs = 2000

function discoverOwners(
  renderer: Window,
  owner: string,
  candidates: string[],
  expired: (owners: string[]) => void
): () => void {
  const relay = renderer.hermesDesktop?.windowRelay

  if (!relay) {
    // Without discovery, absence is not evidence that a peer has closed.
    return () => {}
  }

  const request = randomUuid()
  const replies = new Set<string>()
  let pending = true

  const stop = relay.onMessage(payload => {
    if (!payload || typeof payload !== 'object') { return }
    const message = payload as Record<string, unknown>

    if (message.scope !== presenceScope || typeof message.request !== 'string') { return }

    if (message.kind === 'probe') {
      relay.send({ scope: presenceScope, kind: 'reply', request: message.request, owner })
    } else if (pending && message.kind === 'reply' && message.request === request
      && typeof message.owner === 'string' && candidates.includes(message.owner)) {
      replies.add(message.owner)
    }
  })

  const timer = setTimeout(() => {
    pending = false
    expired(candidates.filter(candidate => !replies.has(candidate)))
  }, presenceTimeoutMs)

  try {
    relay.send({ scope: presenceScope, kind: 'probe', request })
  } catch {
    // A broken transport cannot establish absence either.
    clearTimeout(timer)
    pending = false
  }

  return () => {
    pending = false
    clearTimeout(timer)
    stop()
  }
}

const plugin: HermesPlugin = {
  id: 'flexpair-color-palette',
  name: 'Flexpair Color Palette',
  description:
    'Start in dark mode with fixed Flexpair accents and 150% desktop zoom. No picker or color commands.',
  defaultEnabled: true,
  register(ctx) {
    const window = globalThis.window
    let disposed = false

    let stopPresence = () => {}

    let stopReleaseNotifications = () => {}

    // Serialize the complete shared baseline and mode transaction across renderers.
    // Hosts without Web Locks retain the synchronous single-window path.
    const withPaletteTransaction = (run: () => void) => {
      const locks = window.navigator.locks

      if (locks) {
        void locks.request('flexpair-color-palette:preferences:v1', run).catch(error => {
          console.error('[flexpair-color-palette] Appearance transaction failed', error)
        })
      } else {
        run()
      }
    }

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

      // Socket liveness is not routing authority: a named live route remains
      // known while disconnected, including when this plugin was disabled.
      // Only the initial default placeholder needs a boot-profile hint.
      const bootProfile = new URLSearchParams(window.location.search).get('profile')?.trim()
        || desktopWindow.hermesDesktop?.localSkin?.profile
        || window.localStorage.getItem('hermes-desktop-active-profile-v1')
        || host.state.profile.get()

      const liveProfile = host.state.profile.get().trim()

      // The registry retains routing identity when reconnect clears the
      // public descriptor; socket state and connectionId alone lose that fact.
      const profile = (liveProfile !== 'default' || host.activeConnectionId() !== null
        || host.state.gateway.get() === 'open'
        ? liveProfile : bootProfile)?.trim() || 'default'

      const profiles = profile === 'default' ? [] : [profile]
      const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'
      // Capture the renderer slot and route before the pending lock can yield.
      const owner = registrationOwner(window, profile)
      const ownerGeneration = randomUuid()
      const releasePrefix = `${baselineKey}:released:`
      withPaletteTransaction(() => {
      if (disposed) { return }

      try {
      const modes = readModes()
      let baseline = readBaseline(window, baselineKey)
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

      // Old versions stored profile names, not renderer identities. Preserve
      // those owners indefinitely: a new UUID cannot prove the old window closed.
      const owners: Record<string, string> = Array.isArray(baseline.owners)
        ? Object.fromEntries(baseline.owners
          .filter((legacyProfile): legacyProfile is string => typeof legacyProfile === 'string')
          .map(legacyProfile => [`${legacyOwnerPrefix}${legacyProfile}`, legacyProfile]))
        : baseline.owners ?? {}

      const generations = baseline.generations ?? {}

      const discoveryGenerations: Record<string, string | undefined> = Object.fromEntries(
        Object.keys(owners)
          .filter(id => id !== owner && !id.startsWith(legacyOwnerPrefix))
          .map(id => [id, generations[id]])
      )

      baseline.owners = { ...owners, [owner]: profile }
      baseline.generations = { ...generations, [owner]: ownerGeneration }
      window.localStorage.setItem(baselineKey, JSON.stringify(baseline))

      const restoreProfiles = (remaining: Baseline, activeProfiles: string[], hasLegacyOwners: boolean) => {
        const currentModes = readModes()

        for (const [profile, previous] of Object.entries(remaining.profiles)) {
          if (hasLegacyOwners || activeProfiles.includes(profile) || currentModes[profile] !== 'dark') {
            continue
          }

          if (previous === null) {
            delete currentModes[profile]
          } else {
            currentModes[profile] = previous
          }
        }

        window.localStorage.setItem(profilesKey, JSON.stringify(currentModes))

        for (const target of Object.keys(remaining.profiles)) {
          if (!hasLegacyOwners && !activeProfiles.includes(target)) {
            delete remaining.profiles[target]
          }
        }
      }

      const collectReleaseMarkers = (
        remaining: Baseline,
        releases: Record<string, string | undefined>
      ) => {
        const notifiedOwners: string[] = []
        const markers: string[] = []

        // A separate key per activation is safe to write synchronously during
        // unload. Shared ownership is still changed only under the Web Lock.
        for (let index = 0; index < window.localStorage.length; index++) {
          const marker = window.localStorage.key(index)

          if (!marker?.startsWith(releasePrefix)) { continue }

          try {
            const saved = JSON.parse(window.localStorage.getItem(marker) ?? 'null')

            if (typeof saved?.owner === 'string' && typeof saved.generation === 'string'
              && remaining.generations?.[saved.owner] === saved.generation) {
              releases[saved.owner] = saved.generation
              notifiedOwners.push(saved.owner)
            }

            markers.push(marker)
          } catch {
            // Ignore damaged notification records.
          }
        }

        return { notifiedOwners, markers }
      }

      // A registration owns only its selected profile, not the origin-wide history.
      const releaseOwners = (released: string[], expectedGenerations: Record<string, string | undefined>) => {
        withPaletteTransaction(() => {
        try {
          // Re-read shared ownership before restoring the selected profile.
          const remaining = readBaseline(window, baselineKey)

          if (!remaining) { return }
          let removed = false
          const releases = { ...expectedGenerations }
          const { notifiedOwners, markers } = collectReleaseMarkers(remaining, releases)

          for (const id of new Set([...released, ...notifiedOwners])) {
            if (!Object.hasOwn(remaining.owners ?? {}, id)
              || remaining.generations?.[id] !== releases[id]) { continue }

            delete remaining.owners?.[id]
            delete remaining.generations?.[id]
            removed = true
          }

          if (!removed) {
            markers.forEach(marker => window.localStorage.removeItem(marker))

            return
          }

          const activeProfiles = Object.values(remaining.owners ?? {})
          const hasLegacyOwners = Object.keys(remaining.owners ?? {}).some(id => id.startsWith(legacyOwnerPrefix))
          restoreProfiles(remaining, activeProfiles, hasLegacyOwners)

          if (!activeProfiles.length && !hasLegacyOwners && window.localStorage.getItem(key) === 'dark') {
            if (remaining.global === null) {
              window.localStorage.removeItem(key)
            } else {
              window.localStorage.setItem(key, remaining.global)
            }
          }

          if (activeProfiles.length || hasLegacyOwners) {
            window.localStorage.setItem(baselineKey, JSON.stringify(remaining))
          } else {
            window.localStorage.removeItem(baselineKey)
          }

          window.dispatchEvent(new StorageEvent('storage', { key, newValue: window.localStorage.getItem(key) }))
          markers.forEach(marker => window.localStorage.removeItem(marker))
        } catch (error) {
          console.error('[flexpair-color-palette] Could not restore appearance preferences', error)
        }
        })
      }

      for (const profile of profiles) {
        modes[profile] = 'dark'
      }

      window.localStorage.setItem(profilesKey, JSON.stringify(modes))
      window.localStorage.setItem(key, 'dark')
      // Repaint even when the global fallback was already dark: the current
      // profile or in-memory manual selection may still be light.
      window.dispatchEvent(new StorageEvent('storage', { key, newValue: 'dark' }))

      restoreMode = () => {
        try {
          window.localStorage.setItem(`${releasePrefix}${ownerGeneration}`,
            JSON.stringify({ owner, generation: ownerGeneration }))
        } catch (error) {
          console.error('[flexpair-color-palette] Could not persist appearance release', error)
        }

        releaseOwners([owner], { [owner]: ownerGeneration })
      }

      const onRelease = (event: StorageEvent) => {
        if (event.key?.startsWith(releasePrefix) && event.newValue !== null) {
          releaseOwners([], {})
        }
      }

      window.addEventListener('storage', onRelease)
      stopReleaseNotifications = () => window.removeEventListener('storage', onRelease)
      stopPresence = discoverOwners(window, owner,
        Object.keys(discoveryGenerations), expired => releaseOwners(expired, discoveryGenerations))
      } catch (error) {
        console.error('[flexpair-color-palette] Could not initialize dark preferences', error)
      }
      })
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
    const close = () => dispose(false)

    const dispose = (resetZoom = true) => {
      if (disposed) {
        return
      }

      disposed = true
      stopPresence()
      stopReleaseNotifications()
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
