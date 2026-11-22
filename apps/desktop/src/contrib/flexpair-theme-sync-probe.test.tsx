import { act, cleanup, render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { captureOwnPreferences, hydrateFromSnapshot, startUiPreferencesSync, type UiPreferencesSnapshot } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'
import { ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const modeKey = 'hermes-desktop-mode-v1'
const snapshot: UiPreferencesSnapshot = {
  exists: true, generation: 'g1', revision: 1, values: { [modeKey]: 'light' }
}

it.each([false, true])('keeps startup dark when sync connects (native pin=%s)', async nativePin => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  $activeGatewayProfile.set('default')
  $gatewayState.set('open')
  const disposers: (() => void)[] = []
  const setPercent = vi.fn()
  const setNativeTheme = vi.fn()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent }, setNativeTheme } })
  captureOwnPreferences()
  hydrateFromSnapshot(snapshot)
  const stop = startUiPreferencesSync({
    snapshot,
    read: async () => snapshot,
    write: async () => snapshot,
  })
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  if (nativePin) { window.hermesDesktop?.setNativeTheme?.('dark') }
  expect(window.localStorage.getItem(modeKey)).toBe('dark')
  let theme!: ReturnType<typeof useTheme>
  function Probe() { theme = useTheme(); return null }
  try {
    render(<ThemeProvider><Probe /></ThemeProvider>)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
    console.log('OBSERVED', JSON.stringify({ nativePin, mode: theme.mode, stored: window.localStorage.getItem(modeKey), zoomCalls: setPercent.mock.calls, nativeCalls: setNativeTheme.mock.calls }))
    expect(theme.mode).toBe('dark')
    expect(window.localStorage.getItem(modeKey)).toBe('dark')
  } finally {
    cleanup()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
  }
})

it.each([false, true])('keeps startup dark after another preference updates (native pin=%s)', async nativePin => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  $activeGatewayProfile.set('default')
  $gatewayState.set('open')
  const disposers: (() => void)[] = []
  const setPercent = vi.fn()
  const setNativeTheme = vi.fn()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent }, setNativeTheme } })
  captureOwnPreferences()
  hydrateFromSnapshot(snapshot)
  let onChanged: (next: UiPreferencesSnapshot) => void = () => {}
  const stop = startUiPreferencesSync({
    snapshot,
    read: async () => snapshot,
    write: async () => snapshot,
    onChanged: listener => { onChanged = listener; return () => {} },
  })
  let theme!: ReturnType<typeof useTheme>
  function Probe() { theme = useTheme(); return null }
  try {
    render(<ThemeProvider><Probe /></ThemeProvider>)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
    act(() => {
      plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
      if (nativePin) { window.hermesDesktop?.setNativeTheme?.('dark') }
    })
    expect(theme.mode).toBe('dark')
    expect(window.localStorage.getItem(modeKey)).toBe('dark')
    act(() => onChanged({ ...snapshot, revision: 2, values: {
      [modeKey]: 'light', 'hermes.desktop.sessionListDensity': 'detailed'
    } }))
    console.log('UPDATE', JSON.stringify({ nativePin, mode: theme.mode, stored: window.localStorage.getItem(modeKey), zoomCalls: setPercent.mock.calls, nativeCalls: setNativeTheme.mock.calls }))
    expect(theme.mode).toBe('dark')
  } finally {
    cleanup()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
  }
})
