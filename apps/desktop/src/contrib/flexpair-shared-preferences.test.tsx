import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { act, cleanup, render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../electron/ui-preferences'
import { bootRenderer } from '../lib/ui-preferences/boot'
import type { UiPreferencesSnapshot } from '../lib/ui-preferences/sync'

const MODE = 'hermes-desktop-mode-v1'
const PROFILES = 'hermes-desktop-profile-modes-v1'
const BASELINE = 'hermes-desktop-flexpair-palette-baseline-v1'
const writeOperations: Promise<UiPreferencesSnapshot>[] = []

const advance = async () => {
  for (let attempt = 0; attempt < 3; attempt++) {
    await vi.advanceTimersByTimeAsync(500)
    await Promise.all(writeOperations.splice(0))
  }
}

it('loads the bundled plugin before sync settles, merges peer profiles and respects manual mode changes', async () => {
  writeOperations.length = 0
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-shared-'))
  const file = path.join(dir, 'preferences.json')
  const setPercent = vi.fn()

  let notify: (snapshot: UiPreferencesSnapshot) => void = () => {}

  let releaseWrites = () => {}
  const gate = new Promise<void>(resolve => { releaseWrites = resolve })

  const write = (payload: Parameters<typeof parseUiPreferencesWrite>[0]) => {
    const request = parseUiPreferencesWrite(payload)

    const operation = (async () => {
      if (!request.seed) { await gate }

      return writeUiPreferences(file, request)
    })()

    writeOperations.push(operation)

    return operation
  }

  window.localStorage.clear()
  window.sessionStorage.clear()
  window.localStorage.setItem('hermes.desktop.pluginDecisions.v2', JSON.stringify({
    'provider-card-filter': false, 'hermes-bots': false, kanban: false, radio: false
  }))
  await writeUiPreferences(file, { values: {
    [MODE]: 'light', [PROFILES]: JSON.stringify({ work: 'system', research: 'light', other: 'light' })
  } })
  window.localStorage.setItem('hermes:ui-preferences:generation', readUiPreferences(file).generation!)
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: {
    localSkin: { profile: 'work' }, zoom: { setPercent }, logLine: vi.fn(),
    onPreviewFileChanged: () => () => undefined,
    desktopPluginsRoot: async () => '/isolated-empty-plugins',
    readDir: async () => ({ entries: [] }),
    watchDirectory: async () => ({ id: 'empty-root-watch' }),
    uiPreferences: {
      snapshot: readUiPreferences(file),
      read: async () => readUiPreferences(file),
      write,
      onChanged: (listener: typeof notify) => { notify = listener;

 return () => {} }
    }
  } })
  const desktopBridge = window.hermesDesktop

  try {
    vi.useFakeTimers()

    const app = await bootRenderer(async () => {
      const loader = await import('./plugins')
      const store = await import('./plugins-store')
      const profile = await import('../store/profile')
      const session = await import('../store/session')
      const context = await import('../themes/context')
      const plugin = (await import('../plugins/flexpair-color-palette/plugin')).default
      const { createPluginContext } = await import('./plugin')
      profile.$activeGatewayProfile.set('work')
      session.$gatewayState.set('open')
      loader.discoverBundledPlugins()

      return { context, createPluginContext, plugin, profile, store }
    })

    expect(app.store.$pluginRecords.get()['flexpair-color-palette'].status).toBe('loaded')
    let theme!: ReturnType<typeof app.context.useTheme>

    function Probe() { theme = app.context.useTheme();

 return null }

    render(<app.context.ThemeProvider><Probe /></app.context.ThemeProvider>)
    expect(theme.mode).toBe('dark')
    expect(setPercent.mock.calls).toEqual([[150]])
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })

    // This renderer has an unsent work edit when a peer changes another
    // profile. The pending JSON record must be rebased, not replaced whole.
    const peer = await writeUiPreferences(file, { values: {
      [PROFILES]: JSON.stringify({ work: 'system', research: 'light', other: 'dark', peer: 'system' })
    } })

    act(() => notify(peer))
    releaseWrites()
    await act(advance)
    expect(JSON.parse(readUiPreferences(file).values[PROFILES])).toEqual({
      work: 'dark', research: 'light', other: 'dark', peer: 'system'
    })
    expect(readUiPreferences(file).values[MODE]).toBe('dark')

    // A second renderer owns research; disabling work must leave it alone.
    const peerDisposers: (() => void)[] = []
    window.sessionStorage.clear()
    app.profile.$activeGatewayProfile.set('research')
    Reflect.deleteProperty(window, 'hermesDesktop')
    act(() => app.plugin.register(app.createPluginContext(app.plugin.id, dispose => peerDisposers.push(dispose))))
    await act(advance)
    const sharedOwners = JSON.parse(readUiPreferences(file).values[BASELINE]).owners as Record<string, string>
    expect(Object.keys(sharedOwners).some(owner => owner.startsWith('desktop:'))).toBe(true)
    expect(Object.keys(sharedOwners).some(owner => owner.startsWith('web:'))).toBe(true)
    await act(async () => { await app.store.setPluginEnabled(app.plugin.id, false) })
    await act(advance)
    expect(JSON.parse(readUiPreferences(file).values[PROFILES])).toEqual({
      work: 'dark', research: 'dark', other: 'dark', peer: 'system'
    })
    expect(readUiPreferences(file).values[MODE]).toBe('dark')
    expect(Object.keys(JSON.parse(readUiPreferences(file).values[BASELINE]).owners))
      .toEqual(Object.keys(sharedOwners).filter(owner => owner.startsWith('web:')))
    act(() => peerDisposers.forEach(dispose => dispose()))
    await act(advance)
    expect(readUiPreferences(file).values[MODE]).toBe('light')
    expect(JSON.parse(readUiPreferences(file).values[PROFILES])).toEqual({
      work: 'system', research: 'light', other: 'dark', peer: 'system'
    })

    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: desktopBridge })
    app.profile.$activeGatewayProfile.set('work')
    await act(async () => { await app.store.setPluginEnabled(app.plugin.id, true) })
    expect(theme.mode).toBe('dark')
    act(() => theme.setMode('light'))
    await act(advance)
    expect(theme.mode).toBe('light')
    expect(readUiPreferences(file).values[MODE]).toBe('light')
    expect(setPercent.mock.calls.filter(([value]) => value === 150)).toHaveLength(2)
    await act(async () => { await app.store.setPluginEnabled(app.plugin.id, false) })
    await act(advance)
    expect(readUiPreferences(file).values[MODE]).toBe('light')
    expect(JSON.parse(readUiPreferences(file).values[PROFILES]).work).toBe('light')
  } finally {
    releaseWrites()
    cleanup()
    window.localStorage.clear()
    window.sessionStorage.clear()
    Reflect.deleteProperty(window, 'hermesDesktop')
    vi.useRealTimers()
    fs.rmSync(dir, { force: true, recursive: true })
  }
}, 30_000)
