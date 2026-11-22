import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { act, cleanup, render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../electron/ui-preferences'
import { captureOwnPreferences, hydrateFromSnapshot, startUiPreferencesSync } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'
import { ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

it.each([false, true])('native stored light survives plugin boot and reapplies on sync (native pin=%s)', async nativePin => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-theme-probe-'))
  const file = path.join(dir, 'ui-preferences.json')
  const modeKey = 'hermes-desktop-mode-v1'
  const disposers: (() => void)[] = []
  const setPercent = vi.fn()
  const setNativeTheme = vi.fn()
  let stop = () => {}
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
    $activeGatewayProfile.set('default')
    $gatewayState.set('open')
    await writeUiPreferences(file, { values: { [modeKey]: 'light' } })
    const snapshot = readUiPreferences(file)
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent }, setNativeTheme } })
    captureOwnPreferences()
    hydrateFromSnapshot(snapshot)
    stop = startUiPreferencesSync({
      snapshot,
      read: async () => readUiPreferences(file),
      write: payload => writeUiPreferences(file, parseUiPreferencesWrite(payload)),
    })
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    if (nativePin) { window.hermesDesktop?.setNativeTheme?.('dark') }
    expect(window.localStorage.getItem(modeKey)).toBe('dark')
    let theme!: ReturnType<typeof useTheme>
    function Probe() { theme = useTheme(); return null }
    render(<ThemeProvider><Probe /></ThemeProvider>)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 400)) })
    console.log('REAL_NATIVE_STORE', JSON.stringify({ nativePin, mode: theme.mode, stored: window.localStorage.getItem(modeKey), nativeStored: readUiPreferences(file).values[modeKey], zoomCalls: setPercent.mock.calls, nativeCalls: setNativeTheme.mock.calls }))
    expect(theme.mode).toBe('dark')
    expect(readUiPreferences(file).values[modeKey]).toBe('dark')
  } finally {
    cleanup()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it.each(['absent', 'light'])('checks startup against a %s native preference', async original => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-theme-control-'))
  const file = path.join(dir, 'ui-preferences.json')
  const modeKey = 'hermes-desktop-mode-v1'
  const disposers: (() => void)[] = []
  const setPercent = vi.fn()
  let stop = () => {}
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
    $activeGatewayProfile.set('default')
    $gatewayState.set('open')
    if (original === 'light') { await writeUiPreferences(file, { values: { [modeKey]: 'light' } }) }
    const snapshot = readUiPreferences(file)
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent } } })
    captureOwnPreferences()
    hydrateFromSnapshot(snapshot)
    stop = startUiPreferencesSync({
      snapshot,
      read: async () => readUiPreferences(file),
      write: payload => writeUiPreferences(file, parseUiPreferencesWrite(payload)),
    })
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    let theme!: ReturnType<typeof useTheme>
    function Probe() { theme = useTheme(); return null }
    render(<ThemeProvider><Probe /></ThemeProvider>)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 400)) })
    console.log('CONTROL', JSON.stringify({ original, mode: theme.mode, stored: window.localStorage.getItem(modeKey), nativeStored: readUiPreferences(file).values[modeKey] ?? null, zoomCalls: setPercent.mock.calls }))
    expect(theme.mode).toBe('dark')
    expect(readUiPreferences(file).values[modeKey]).toBe('dark')
  } finally {
    cleanup()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it('persists the plugin startup without a native desktop bridge', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-theme-control-'))
  const file = path.join(dir, 'ui-preferences.json')
  const modeKey = 'hermes-desktop-mode-v1'
  const disposers: (() => void)[] = []
  let stop = () => {}
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
    $activeGatewayProfile.set('default')
    $gatewayState.set('open')
    await writeUiPreferences(file, { values: { [modeKey]: 'light' } })
    const snapshot = readUiPreferences(file)
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
    captureOwnPreferences()
    hydrateFromSnapshot(snapshot)
    stop = startUiPreferencesSync({
      snapshot,
      read: async () => readUiPreferences(file),
      write: payload => writeUiPreferences(file, parseUiPreferencesWrite(payload)),
    })
    let theme!: ReturnType<typeof useTheme>
    function Probe() { theme = useTheme(); return null }
    render(<ThemeProvider><Probe /></ThemeProvider>)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 400)) })
    act(() => {
      plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 400)) })
    console.log('HOST_OBSERVED', JSON.stringify({ mode: theme.mode, stored: window.localStorage.getItem(modeKey), nativeStored: readUiPreferences(file).values[modeKey] }))
    expect(theme.mode).toBe('dark')
    expect(readUiPreferences(file).values[modeKey]).toBe('dark')
  } finally {
    cleanup()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
