import { act, cleanup, render } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import plugin from '../plugins/flexpair-color-palette/plugin'
import { setPrimaryGateway, setPrimaryGatewayConnectionId } from '../store/gateway'
import { $activeGatewayProfile } from '../store/profile'
import { $connection, $gatewayState } from '../store/session'
import { modePref, ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const disposers: (() => void)[] = []

it('initializes and restores appearance when randomUUID is unavailable', () => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  $gatewayState.set('open')
  $activeGatewayProfile.set('work')
  modePref.assign('default', 'light')
  modePref.assign('work', 'light')
  vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })

  act(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))))
  expect(modePref.resolve('default')).toBe('dark')
  expect(modePref.resolve('work')).toBe('dark')

  act(() => { disposers.splice(0).forEach(dispose => dispose()) })
  expect(modePref.resolve('default')).toBe('light')
  expect(modePref.resolve('work')).toBe('light')
})

it('still releases preferences and resets zoom when the release notification cannot be saved', () => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  $gatewayState.set('open')
  $activeGatewayProfile.set('work')
  modePref.assign('work', 'light')
  const setPercent = vi.fn()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent } } })
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  const storage = window.localStorage
  const original = storage.setItem.bind(storage)
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  let releaseNotificationWriteRejected = false

  const write = vi.fn((key: string, value: string) => {
    if (key.includes(':released:')) {
      releaseNotificationWriteRejected = true
      throw new Error('quota exceeded')
    }
    original(key, value)
  })
  const descriptor = Object.getOwnPropertyDescriptor(window, 'localStorage')!
  // Native Storage is an exotic object; use the same own-method shape as
  // the Node fallback so interception is observable in either environment.
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    get length() { return storage.length },
    key: storage.key.bind(storage),
    getItem: storage.getItem.bind(storage),
    setItem: write,
    removeItem: storage.removeItem.bind(storage),
    clear: storage.clear.bind(storage)
  } })

  try {
    expect(() => disposers.splice(0).forEach(dispose => dispose())).not.toThrow()
    expect(releaseNotificationWriteRejected).toBe(true)
    expect(modePref.resolve('work')).toBe('light')
    expect(setPercent).toHaveBeenLastCalledWith(0)
  } finally {
    Object.defineProperty(window, 'localStorage', descriptor)
    error.mockRestore()
  }
})

it.each(['reply', 'foreign-scope', 'wrong-request', 'late', 'dispose', 'no-transport'] as const)(
  'bounds owner discovery with %s', behavior => {
    vi.useFakeTimers()
    window.localStorage.clear()
    window.sessionStorage.clear()
    $gatewayState.set('open')
    $activeGatewayProfile.set('work')
    const key = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'

    let receive: (message: unknown) => void = () => {}
    const send = vi.fn()
    const stop = vi.fn()
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: {
      windowRelay: {
        send,
        onMessage: (callback: typeof receive) => { receive = callback;

 return stop }
      }
    } })
    modePref.assign('work', 'light')
    modePref.assign('research', 'light')
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    const dead = Object.keys(JSON.parse(window.localStorage.getItem(key)!).owners)[0]
    disposers.splice(0)
    window.sessionStorage.clear()
    $activeGatewayProfile.set('research')

    if (behavior === 'no-transport') {
      Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
    }

    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    const probe = send.mock.calls.at(-1)![0]
    const reply = { ...probe, kind: 'reply', owner: dead }
    receive(null)
    receive({ ...reply, owner: 123 })

    if (behavior === 'reply') { receive(reply) }

    if (behavior === 'foreign-scope') { receive({ ...reply, scope: 'other-plugin' }) }

    if (behavior === 'wrong-request') { receive({ ...reply, request: 'unrelated' }) }

    if (behavior === 'dispose') { disposers.splice(0).forEach(dispose => dispose()) }
    expect(modePref.resolve('work')).toBe('dark')
    vi.advanceTimersByTime(1999)
    expect(modePref.resolve('work')).toBe('dark')
    vi.advanceTimersByTime(1)

    if (behavior === 'late') { receive(reply) }
    const retained = ['reply', 'dispose', 'no-transport'].includes(behavior)
    expect(modePref.resolve('work')).toBe(retained ? 'dark' : 'light')

    if (behavior === 'dispose') { expect(stop).toHaveBeenCalledTimes(1) }

    if (behavior !== 'no-transport' && behavior !== 'dispose') {
      send.mockClear()
      receive({ scope: probe.scope, kind: 'probe', request: 'peer-request' })
      expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: 'reply', request: 'peer-request' }))
    }

    disposers.splice(0).forEach(dispose => dispose())
    expect(modePref.resolve('research')).toBe('light')
    vi.useRealTimers()
  }
)

it.each(['fresh-session', 'profile-changed'] as const)('recovers an abandoned owner after %s', lifecycle => {
  vi.useFakeTimers()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: {
    windowRelay: { send: vi.fn(), onMessage: () => () => {} }
  } })
  window.localStorage.clear()
  $gatewayState.set('open')
  modePref.assign('work', 'light')
  modePref.assign('research', 'light')
  $activeGatewayProfile.set('work')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  // The dead renderer cannot deliver unload or disposal callbacks.
  disposers.splice(0)

  if (lifecycle === 'fresh-session') {
    window.sessionStorage.clear()
  } else {
    $activeGatewayProfile.set('research')
  }

  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.advanceTimersByTime(2000)
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve('work')).toBe('light')
  expect(modePref.resolve('research')).toBe('light')
  expect(modePref.resolve('default')).toBe('light')
  vi.useRealTimers()
})

it('keeps the reloaded owner dark when a peer discovery expires', () => {
  vi.useFakeTimers()
  const firstWindow = window
  const frame = document.createElement('iframe')
  document.body.append(frame)
  const secondWindow = frame.contentWindow!
  Object.defineProperty(secondWindow, 'localStorage', { configurable: true, value: firstWindow.localStorage })
  const secondSession = new Map<string, string>()
  Object.defineProperty(secondWindow, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => secondSession.get(key) ?? null,
    setItem: (key: string, value: string) => secondSession.set(key, value)
  } })
  type Listener = (message: unknown) => void
  const listeners = new Map<Window, Set<Listener>>()
  const probes: Array<{ from: Window, request: string }> = []

  for (const renderer of [firstWindow, secondWindow]) {
    Object.defineProperty(renderer, 'hermesDesktop', { configurable: true, value: { windowRelay: {
      send: (message: { kind: string, request: string }) => {
        if (message.kind === 'probe') { probes.push({ from: renderer, request: message.request }) }

        for (const [peer, callbacks] of listeners) {
          if (peer !== renderer) { callbacks.forEach(callback => callback(message)) }
        }
      },
      onMessage: (callback: Listener) => {
        const callbacks = listeners.get(renderer) ?? new Set<Listener>()
        callbacks.add(callback)
        listeners.set(renderer, callbacks)

        return () => callbacks.delete(callback)
      }
    } } })
  }

  const firstDisposers: (() => void)[] = []
  const secondDisposers: (() => void)[] = []

  const register = (renderer: Window, profile: string, owned: (() => void)[]) => {
    vi.stubGlobal('window', renderer)
    $activeGatewayProfile.set(profile)
    plugin.register(createPluginContext(plugin.id, dispose => owned.push(dispose)))
  }

  const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'
  const sessionKey = 'hermes-desktop-plugin-flexpair-color-palette-window-v1'

  try {
    firstWindow.localStorage.clear()
    firstWindow.sessionStorage.clear()
    firstWindow.sessionStorage.setItem(sessionKey, 'stable-window-id')
    secondSession.set(sessionKey, 'peer-window-id')
    modePref.assign('work', 'light')
    modePref.assign('research', 'light')
    modePref.assign('default', 'light')
    $gatewayState.set('open')
    register(firstWindow, 'work', firstDisposers)
    const original = JSON.parse(firstWindow.localStorage.getItem(baselineKey)!)
    // Crash drops the listener and timer without disposal; the session slot survives.
    firstDisposers.splice(0)
    listeners.get(firstWindow)?.clear()
    vi.clearAllTimers()
    register(secondWindow, 'research', secondDisposers)
    const missedRequest = probes.at(-1)!.request
    register(firstWindow, 'work', firstDisposers)
    expect(probes.at(-1)!.request).not.toBe(missedRequest)
    expect(firstWindow.sessionStorage.getItem(sessionKey)).toBe('stable-window-id')
    vi.advanceTimersByTime(2000)
    expect(modePref.resolve('work')).toBe('dark')
    expect(modePref.resolve('research')).toBe('dark')
    const recovered = JSON.parse(firstWindow.localStorage.getItem(baselineKey)!)
    expect(recovered.owners['stable-window-id:work']).toBe('work')
    expect(recovered.generations['stable-window-id:work']).not.toBe(original.generations['stable-window-id:work'])
    firstDisposers.splice(0).forEach(dispose => dispose())
    expect(modePref.resolve('work')).toBe('light')
    expect(modePref.resolve('research')).toBe('dark')
    secondDisposers.splice(0).forEach(dispose => dispose())
    expect(modePref.resolve('research')).toBe('light')
    expect(modePref.resolve('default')).toBe('light')
    expect(firstWindow.localStorage.getItem(baselineKey)).toBeNull()
  } finally {
    vi.stubGlobal('window', firstWindow)
    secondDisposers.splice(0).forEach(dispose => dispose())
    firstDisposers.splice(0).forEach(dispose => dispose())
    frame.remove()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  }
})

it.each(['work', 'research'])('serializes overlapping registrations and releases for %s peers', async (secondProfile) => {
  const jobs: Array<() => void> = []

  const request = vi.fn((_name: string, run: () => void) => new Promise<void>((resolve, reject) => {
    jobs.push(() => { try { run(); resolve() } catch (error) { reject(error) } })
  }))

  Object.defineProperty(window.navigator, 'locks', { configurable: true, value: { request } })
  const firstDisposers: (() => void)[] = []
  const secondDisposers: (() => void)[] = []
  const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'

  const register = (id: string, profile: string, owned: (() => void)[]) => {
    window.sessionStorage.setItem('hermes-desktop-plugin-flexpair-color-palette-window-v1', id)
    $activeGatewayProfile.set(profile)
    plugin.register(createPluginContext(plugin.id, dispose => owned.push(dispose)))
  }

  const drain = async () => {
    while (jobs.length) { jobs.shift()!() }
    await Promise.resolve()
  }

  try {
    window.localStorage.clear()
    modePref.assign('work', 'light')
    modePref.assign('research', 'system')
    modePref.assign('default', 'light')
    $gatewayState.set('open')
    register('first-peer', 'work', firstDisposers)
    register('second-peer', secondProfile, secondDisposers)
    expect(jobs).toHaveLength(2)
    await drain()
    const baseline = JSON.parse(window.localStorage.getItem(baselineKey)!)
    expect(Object.keys(baseline.owners)).toHaveLength(2)
    expect(baseline.profiles.work).toBe('light')

    if (secondProfile === 'research') { expect(baseline.profiles.research).toBe('system') }
    expect(modePref.resolve('work')).toBe('dark')
    expect(modePref.resolve(secondProfile)).toBe('dark')
    firstDisposers.splice(0).forEach(dispose => dispose())
    await drain()
    expect(modePref.resolve(secondProfile)).toBe('dark')
    secondDisposers.splice(0).forEach(dispose => dispose())
    await drain()
    expect(modePref.resolve('work')).toBe('light')
    expect(modePref.resolve('research')).toBe('system')
    expect(window.localStorage.getItem(baselineKey)).toBeNull()
    // Both releases are queued before either gets the shared lock.
    register('first-peer', 'work', firstDisposers)
    register('second-peer', secondProfile, secondDisposers)
    await drain()
    firstDisposers.splice(0).forEach(dispose => dispose())
    secondDisposers.splice(0).forEach(dispose => dispose())
    expect(jobs).toHaveLength(2)
    await drain()
    expect(modePref.resolve('work')).toBe('light')
    expect(modePref.resolve('research')).toBe('system')
    expect(modePref.resolve('default')).toBe('light')
    expect(window.localStorage.getItem(baselineKey)).toBeNull()
    // Disposal before a pending registration acquires the lock cannot leave an owner.
    register('cancelled-peer', 'work', firstDisposers)
    firstDisposers.splice(0).forEach(dispose => dispose())
    await drain()
    expect(modePref.resolve('work')).toBe('light')
    expect(window.localStorage.getItem(baselineKey)).toBeNull()
  } finally {
    firstDisposers.splice(0).forEach(dispose => dispose())
    secondDisposers.splice(0).forEach(dispose => dispose())
    await drain()
    Reflect.deleteProperty(window.navigator, 'locks')
  }
})

it('restores shared appearance after a closing renderer loses its queued lock release', async () => {
  const firstWindow = window
  const frame = document.createElement('iframe')
  document.body.append(frame)
  const closingWindow = frame.contentWindow!
  Object.defineProperty(closingWindow, 'localStorage', {
    configurable: true, value: firstWindow.localStorage
  })
  const closingSession = new Map<string, string>()
  Object.defineProperty(closingWindow, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => closingSession.get(key) ?? null,
    setItem: (key: string, value: string) => closingSession.set(key, value)
  } })

  type LockJob = {
    owner: Window
    run: () => unknown
    resolve: () => void
    reject: (error: unknown) => void
  }
  const jobs: LockJob[] = []
  const idleWaiters: (() => void)[] = []
  let active = false

  const signalIdle = () => {
    if (active || jobs.length) { return }
    idleWaiters.splice(0).forEach(resolve => resolve())
  }

  const runNext = () => {
    if (active || !jobs.length) { signalIdle();

 return }

    const job = jobs.shift()!
    active = true
    let result: unknown

    try { result = job.run() } catch (error) {
      job.reject(error)
      active = false
      runNext()

      return
    }

    Promise.resolve(result).then(job.resolve, job.reject).finally(() => {
      active = false
      runNext()
    })
  }

  const whenIdle = () => active || jobs.length
    ? new Promise<void>(resolve => idleWaiters.push(resolve))
    : Promise.resolve()

  const lockName = 'flexpair-color-palette:preferences:v1'

  const locksFor = (owner: Window) => ({
    request: (name: string, run: () => unknown) => new Promise<void>((resolve, reject) => {
      if (name !== lockName) { reject(new Error(`Unexpected lock: ${name}`));

 return }

      jobs.push({ owner, run, resolve, reject })
      runNext()
    })
  })

  const originalLocks = Object.getOwnPropertyDescriptor(firstWindow.navigator, 'locks')
  Object.defineProperty(firstWindow.navigator, 'locks', { configurable: true, value: locksFor(firstWindow) })
  Object.defineProperty(closingWindow.navigator, 'locks', { configurable: true, value: locksFor(closingWindow) })

  const closingDisposers: (() => void)[] = []
  const survivingDisposers: (() => void)[] = []

  const register = (renderer: Window, owned: (() => void)[]) => {
    vi.stubGlobal('window', renderer)
    $activeGatewayProfile.set('work')
    plugin.register(createPluginContext(plugin.id, dispose => owned.push(dispose)))
  }

  let releaseHeldLock: (() => void) | undefined
  let heldRequest: Promise<void> | undefined

  try {
    firstWindow.localStorage.clear()
    firstWindow.sessionStorage.clear()
    closingSession.set('hermes-desktop-plugin-flexpair-color-palette-window-v1', 'closing-window')
    firstWindow.sessionStorage.setItem('hermes-desktop-plugin-flexpair-color-palette-window-v1', 'surviving-window')
    modePref.assign('work', 'light')
    modePref.assign('default', 'light')
    $gatewayState.set('open')

    register(closingWindow, closingDisposers)
    await whenIdle()
    register(firstWindow, survivingDisposers)
    await whenIdle()

    heldRequest = locksFor(firstWindow).request(lockName, () => new Promise<void>(resolve => {
      releaseHeldLock = resolve
    }))
    expect(releaseHeldLock).toBeTypeOf('function')

    closingWindow.dispatchEvent(new Event('pagehide'))
    frame.remove()

    // Simulate teardown dropping queued callbacks that belonged to the destroyed renderer.
    for (const job of jobs.filter(job => job.owner === closingWindow)) {
      jobs.splice(jobs.indexOf(job), 1)
      job.resolve()
    }

    vi.stubGlobal('window', firstWindow)
    survivingDisposers.splice(0).forEach(dispose => dispose())
    releaseHeldLock?.()
    releaseHeldLock = undefined
    await heldRequest
    await whenIdle()

    expect(modePref.resolve('work')).toBe('light')
    expect(modePref.resolve('default')).toBe('light')
    expect(firstWindow.localStorage.getItem('hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1')).toBeNull()
  } finally {
    releaseHeldLock?.()
    await heldRequest
    closingDisposers.splice(0).forEach(dispose => dispose())
    survivingDisposers.splice(0).forEach(dispose => dispose())
    await whenIdle()
    frame.remove()
    vi.unstubAllGlobals()

    if (originalLocks) { Object.defineProperty(firstWindow.navigator, 'locks', originalLocks) }
    else { Reflect.deleteProperty(firstWindow.navigator, 'locks') }

    Reflect.deleteProperty(closingWindow.navigator, 'locks')
  }
})

it('preserves legacy profile owners when migrating persisted ownership', () => {
  vi.useFakeTimers()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'
  window.localStorage.setItem(baselineKey, JSON.stringify({
    global: 'light', profiles: { work: 'light' }, owners: ['work']
  }))
  window.localStorage.setItem('hermes-desktop-mode-v1', 'dark')
  window.localStorage.setItem('hermes-desktop-profile-modes-v1', JSON.stringify({ work: 'dark' }))
  $activeGatewayProfile.set('work')
  $gatewayState.set('open')
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: {
    windowRelay: { send: vi.fn(), onMessage: () => () => {} }
  } })

  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  const migrated = JSON.parse(window.localStorage.getItem(baselineKey)!)
  expect(migrated.owners).toEqual(expect.objectContaining({ 'legacy:work': 'work' }))
  vi.advanceTimersByTime(2000)
  expect(modePref.resolve('work')).toBe('dark')
  expect(JSON.parse(window.localStorage.getItem(baselineKey)!).owners)
    .toEqual(expect.objectContaining({ 'legacy:work': 'work' }))
  disposers.splice(0).forEach(dispose => dispose())

  expect(modePref.resolve('work')).toBe('dark')
  expect(JSON.parse(window.localStorage.getItem(baselineKey)!).owners)
    .toEqual({ 'legacy:work': 'work' })
  vi.useRealTimers()
})

it('retains every baseline while a legacy owner profile does not match saved profiles', () => {
  vi.useFakeTimers()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const baselineKey = 'hermes-desktop-plugin-flexpair-color-palette-mode-baseline-v1'
  window.localStorage.setItem(baselineKey, JSON.stringify({
    global: 'light', profiles: { work: 'light' }, owners: ['research']
  }))
  window.localStorage.setItem('hermes-desktop-mode-v1', 'dark')
  window.localStorage.setItem('hermes-desktop-profile-modes-v1', JSON.stringify({ work: 'dark' }))
  $activeGatewayProfile.set('work')
  $gatewayState.set('open')
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: {
    windowRelay: { send: vi.fn(), onMessage: () => () => {} }
  } })

  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.advanceTimersByTime(2000)
  disposers.splice(0).forEach(dispose => dispose())

  expect(modePref.resolve('work')).toBe('dark')
  expect(JSON.parse(window.localStorage.getItem(baselineKey)!)).toMatchObject({
    global: 'light', profiles: { work: 'light' }, owners: { 'legacy:research': 'research' }
  })
  vi.useRealTimers()
})

it.each(['connecting', 'closed', 'idle'] as const)('re-enables on established default routing while %s despite research boot hints', socketState => {
  window.localStorage.clear()
  window.history.replaceState(null, '', '/?profile=research')
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true, value: { localSkin: { profile: 'research' } }
  })
  modePref.assign('research', 'light')
  modePref.assign('default', 'light')
  $activeGatewayProfile.set('research')
  $gatewayState.set('open')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  disposers.splice(0).forEach(dispose => dispose())
  // Routing lives in the registry; reconnect failure clears only the descriptor.
  setPrimaryGateway(null, 'default')
  setPrimaryGatewayConnectionId('local', 'local')
  $connection.set(null)
  $activeGatewayProfile.set('default')
  $gatewayState.set(socketState)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  expect(modePref.resolve('research')).toBe('light')
  expect(modePref.resolve('default')).toBe('dark')
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve('default')).toBe('light')
  $connection.set(null)
})

it.each(['default', 'work'])('keeps two enabled windows on the same %s profile dark until the last closes', profile => {
  window.localStorage.clear()
  $gatewayState.set('open')
  modePref.assign(profile, 'light')
  const firstWindow = window
  const frame = document.createElement('iframe')
  document.body.append(frame)
  const secondWindow = frame.contentWindow!
  Object.defineProperty(secondWindow, 'localStorage', { configurable: true, value: firstWindow.localStorage })
  // Native top-level renderer windows have independent session storage.
  const session = new Map<string, string>()
  Object.defineProperty(secondWindow, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => session.get(key) ?? null,
    setItem: (key: string, value: string) => session.set(key, value)
  } })
  $activeGatewayProfile.set(profile)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.stubGlobal('window', secondWindow)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.stubGlobal('window', firstWindow)
  firstWindow.dispatchEvent(new Event('pagehide'))
  expect(modePref.resolve(profile)).toBe('dark')
  expect(modePref.resolve('default')).toBe('dark')
  disposers.shift()!()
  firstWindow.dispatchEvent(new Event('beforeunload'))
  expect(modePref.resolve(profile)).toBe('dark')
  vi.stubGlobal('window', secondWindow)
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(profile)).toBe('light')
  expect(modePref.resolve('default')).toBe('light')
  vi.unstubAllGlobals()
  frame.remove()
})

it.each(['pagehide', 'beforeunload'])('releases only the closing window on %s without context disposal', event => {
  window.localStorage.clear()
  $gatewayState.set('open')
  modePref.assign('default', 'light')
  modePref.assign('work', 'light')
  const closing = window
  const remaining = document.createElement('iframe')
  document.body.append(remaining)
  const otherWindow = remaining.contentWindow!
  // Separate renderer lifecycles, shared origin-wide preferences.
  Object.defineProperty(otherWindow, 'localStorage', { configurable: true, value: closing.localStorage })
  // Model the native persistence boundary shared by both renderer bridges.
  let sharedZoomPercent = 100
  const setPercent = vi.fn((percent: number) => { sharedZoomPercent = percent })

  for (const renderer of [closing, otherWindow]) {
    Object.defineProperty(renderer, 'hermesDesktop', {
      configurable: true, value: { zoom: { setPercent } }
    })
  }

  $activeGatewayProfile.set('work')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.stubGlobal('window', otherWindow)
  $activeGatewayProfile.set('default')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  vi.stubGlobal('window', closing)
  setPercent(125)
  closing.dispatchEvent(new Event(event))
  expect(sharedZoomPercent).toBe(125)
  expect(setPercent.mock.calls).toEqual([[150], [150], [125]])
  expect(modePref.resolve('work')).toBe('light')
  expect(modePref.resolve('default')).toBe('dark')
  // Late host disposal of the closed renderer must not consume a new owner.
  disposers.shift()!()
  closing.dispatchEvent(new Event(event === 'pagehide' ? 'beforeunload' : 'pagehide'))
  expect(sharedZoomPercent).toBe(125)
  expect(setPercent.mock.calls).toEqual([[150], [150], [125]])
  vi.stubGlobal('window', otherWindow)
  disposers.splice(0).forEach(dispose => { dispose(); dispose() })
  expect(sharedZoomPercent).toBe(0)
  expect(setPercent.mock.calls).toEqual([[150], [150], [125], [0]])
  expect(modePref.resolve('default')).toBe('light')
  vi.unstubAllGlobals()
  remaining.remove()
})

it.each(['connecting', 'closed', 'idle'] as const)('uses established work routing during %s and disable/re-enable', socketState => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true, value: { localSkin: { profile: 'research' } }
  })
  window.history.replaceState(null, '', '/?profile=research')
  modePref.assign('research', 'light')
  modePref.assign('work', 'light')
  $activeGatewayProfile.set('work')
  $gatewayState.set('open')
  $gatewayState.set(socketState)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  expect(modePref.resolve('work')).toBe('dark')
  expect(modePref.resolve('research')).toBe('light')
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve('work')).toBe('light')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  expect(modePref.resolve('work')).toBe('dark')
  expect(modePref.resolve('research')).toBe('light')
})

it.each(['work', 'research'])('isolates independent registrations when disposing %s first', first => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  $gatewayState.set('open')
  modePref.assign('work', 'light')
  modePref.assign('research', 'light')
  const owned: Record<string, (() => void)[]> = { work: [], research: [] }

  for (const profile of ['work', 'research']) {
    $activeGatewayProfile.set(profile)
    plugin.register(createPluginContext(plugin.id, dispose => owned[profile].push(dispose)))
    expect(modePref.resolve(profile)).toBe('dark')
  }

  const second = first === 'work' ? 'research' : 'work'
  owned[first].splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(first)).toBe('light')
  expect(modePref.resolve(second)).toBe('dark')
  expect(modePref.resolve('default')).toBe('dark')
  owned[second].splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(first)).toBe('light')
  expect(modePref.resolve(second)).toBe('light')
  expect(modePref.resolve('default')).toBe('light')
})

it.each(['default', 'work'])('retains the light restoration baseline across renderer restart without disposal for %s', profile => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  $activeGatewayProfile.set(profile)
  $gatewayState.set('open')
  modePref.assign(profile, 'light')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  expect(modePref.resolve(profile)).toBe('dark')
  // A renderer crash loses callbacks, but not browser storage.
  disposers.splice(0)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(profile)).toBe('light')
  modePref.assign(profile, 'system')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(profile)).toBe('system')
})

it.each(['default', 'work'])('preserves a manual system edit through restart and reload disposal for %s', profile => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  $activeGatewayProfile.set(profile)
  $gatewayState.set('open')
  modePref.assign(profile, 'light')
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  modePref.assign(profile, 'system')
  disposers.splice(0)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  expect(modePref.resolve(profile)).toBe('dark')
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(profile)).toBe('system')
  // Reload has the same public disposal seam as disable.
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  modePref.assign(profile, 'light')
  disposers.splice(0).forEach(dispose => dispose())
  expect(modePref.resolve(profile)).toBe('light')
})

it('starts a pinned work window dark before delayed gateway routing without localSkin', async () => {
  window.localStorage.clear()
  window.history.replaceState(null, '', '/?profile=work')
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  act(() => {
    modePref.assign('work', 'light')
    $activeGatewayProfile.set('default')
    $gatewayState.set('connecting')
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  })
  let theme!: ReturnType<typeof useTheme>

  function Probe() { theme = useTheme();

 return null }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  await act(async () => { $activeGatewayProfile.set('work'); $gatewayState.set('open') })
  expect(theme.mode).toBe('dark')
  expect(modePref.resolve('work')).toBe('dark')
})

it('does not rewrite stale research boot preferences when enabling after live work routing', () => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true, value: { localSkin: { profile: 'research' } }
  })
  act(() => {
    modePref.assign('research', 'light')
    modePref.assign('work', 'light')
    $activeGatewayProfile.set('work')
    $gatewayState.set('open')
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  })
  expect(modePref.resolve('work')).toBe('dark')
  expect(modePref.resolve('research')).toBe('light')
})

it.each([
  ['default', 'light'], ['work', 'light'],
  ['default', 'dark'], ['work', 'dark'],
] as const)('restores the previous preference on disposal for %s (%s)', (profile, previousMode) => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  act(() => {
    modePref.assign('default', previousMode)
    modePref.assign('work', previousMode)
    $activeGatewayProfile.set(profile)
    $gatewayState.set('open')
  })
  let theme!: ReturnType<typeof useTheme>

  function Probe() {
    theme = useTheme()

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  expect(theme.mode).toBe(previousMode)
  act(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))))
  expect(theme.mode).toBe('dark')
  // Edit another profile without changing the global mode (named core assigns
  // also mirror into global, which would be a separate manual mode edit).
  const modesKey = 'hermes-desktop-profile-modes-v1'
  window.localStorage.setItem(modesKey, JSON.stringify({
    ...JSON.parse(window.localStorage.getItem(modesKey) ?? '{}'), unrelated: 'light'
  }))
  act(() => { disposers.splice(0).forEach(dispose => dispose()) })
  expect(theme.mode).toBe(previousMode)
  expect(modePref.resolve(profile)).toBe(previousMode)
  expect(modePref.resolve('unrelated')).toBe('light')
})

afterEach(() => {
  act(() => cleanup())
  act(() => { disposers.splice(0).forEach(dispose => dispose()) })
  vi.unstubAllGlobals()
  act(() => {
    window.localStorage.clear()
    setPrimaryGateway(null, 'default')
    setPrimaryGatewayConnectionId(null)
    $connection.set(null)
    $activeGatewayProfile.set('default')
    $gatewayState.set('idle')
    window.history.replaceState(null, '', '/')
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  })
  vi.restoreAllMocks()
})

it('defaults to dark before provider mount and preserves later manual light through remount', () => {
  window.localStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))

  let theme!: ReturnType<typeof useTheme>

  function Probe() {
    theme = useTheme()

    return null
  }

  const host = () => <StrictMode><ThemeProvider><Probe /></ThemeProvider></StrictMode>
  const mounted = render(host())
  expect(theme.mode).toBe('dark')
  act(() => theme.setMode('light'))
  mounted.unmount()
  render(host())
  expect(theme.mode).toBe('light')
  expect(modePref.resolve('default')).toBe('light')
})

it('recovers dark initialization from malformed saved profile modes', () => {
  window.localStorage.setItem('hermes-desktop-mode-v1', 'light')
  window.localStorage.setItem('hermes-desktop-profile-modes-v1', '{invalid')
  act(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))))
  expect(window.localStorage.getItem('hermes-desktop-mode-v1')).toBe('dark')
  expect(JSON.parse(window.localStorage.getItem('hermes-desktop-profile-modes-v1')!)).toEqual({})
})

it('switches an existing explicit light preference to dark when enabled', () => {
  window.localStorage.clear()
  act(() => {
    modePref.assign('default', 'light')
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  })

  let mode: string | undefined

  function Probe() {
    mode = useTheme().mode

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  expect(mode).toBe('dark')
  expect(modePref.resolve('default')).toBe('dark')
})

it('updates an already mounted provider with a missing default without a plugin surface', () => {
  window.localStorage.clear()

  let mode: string | undefined

  function Probe() {
    mode = useTheme().mode

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  act(() => { plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))) })
  expect(mode).toBe('dark')
})

it('overrides a named profile light preference even when the global default is already dark', () => {
  act(() => {
    modePref.assign('work', 'light')
    modePref.assign('default', 'dark')
    $activeGatewayProfile.set('work')
    $gatewayState.set('open')
  })
  let theme!: ReturnType<typeof useTheme>

  function Probe() {
    theme = useTheme()

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  act(() => theme.setMode('light'))
  act(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))))
  expect(theme.mode).toBe('dark')
  expect(modePref.resolve('work')).toBe('dark')
  act(() => theme.setMode('light'))
  expect(theme.mode).toBe('light')
  act(() => { disposers.splice(0).forEach(dispose => dispose()) })
  act(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))))
  expect(theme.mode).toBe('dark')
})
