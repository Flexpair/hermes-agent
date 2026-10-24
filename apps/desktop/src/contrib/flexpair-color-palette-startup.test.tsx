import { act, cleanup, render } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { modePref, ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const disposers: (() => void)[] = []

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
  act(() => modePref.assign('unrelated', 'light'))
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
