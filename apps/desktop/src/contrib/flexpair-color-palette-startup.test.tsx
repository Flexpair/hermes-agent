import { act, cleanup, render } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'
import { modePref, ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const disposers: (() => void)[] = []

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
  function Probe() { theme = useTheme(); return null }
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
  act(() => {
    window.localStorage.clear()
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
