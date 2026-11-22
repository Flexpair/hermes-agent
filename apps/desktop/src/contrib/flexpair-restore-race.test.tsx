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
const JOINED = 'hermes:ui-preferences:generation'

it('keeps the active palette dark when a peer restore arrives during startup', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-restore-race-'))
  const file = path.join(dir, 'preferences.json')
  const writeOperations: Promise<UiPreferencesSnapshot>[] = []
  const disposers: (() => void)[] = []
  const locksDescriptor = Object.getOwnPropertyDescriptor(window.navigator, 'locks')

  let notify: (snapshot: UiPreferencesSnapshot) => void = () => {}

  let releaseWrites = () => {}
  const gate = new Promise<void>(resolve => { releaseWrites = resolve })

  let writeStarted = () => {}
  const started = new Promise<void>(resolve => { writeStarted = resolve })

  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
    Object.defineProperty(window.navigator, 'locks', { configurable: true, value: undefined })
    vi.useFakeTimers()

    await writeUiPreferences(file, { values: {
      [MODE]: 'dark',
      [PROFILES]: '{}',
      [BASELINE]: JSON.stringify({
        global: 'light',
        profiles: {},
        owners: { 'desktop:old-window': 'default' },
        generations: { 'desktop:old-window': 'old-generation' }
      })
    } })
    const snapshot = readUiPreferences(file)
    window.localStorage.setItem(JOINED, snapshot.generation ?? '')

    const write = (payload: Parameters<typeof parseUiPreferencesWrite>[0]) => {
      const request = parseUiPreferencesWrite(payload)

      const operation = (async () => {
        if (!request.seed) {
          writeStarted()
          await gate
        }

        return writeUiPreferences(file, request)
      })()

      writeOperations.push(operation)

      return operation
    }

    const bridge = {
      snapshot,
      read: async () => readUiPreferences(file),
      write,
      onChanged: (listener: typeof notify) => {
        notify = listener

        return () => {}
      }
    }

    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { uiPreferences: bridge }
    })

    const app = await bootRenderer(async () => {
      const [{ default: plugin }, { createPluginContext }, profile, session, theme] = await Promise.all([
        import('../plugins/flexpair-color-palette/plugin'),
        import('./plugin'),
        import('../store/profile'),
        import('../store/session'),
        import('../themes/context')
      ])

      profile.$activeGatewayProfile.set('default')
      session.$gatewayState.set('open')
      plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
      const restored = await writeUiPreferences(file, { values: { [MODE]: 'light', [BASELINE]: null } })
      notify(restored)

      return { theme }
    })

    let currentTheme!: ReturnType<typeof app.theme.useTheme>

    function Probe() {
      currentTheme = app.theme.useTheme()

      return null
    }

    render(<app.theme.ThemeProvider><Probe /></app.theme.ThemeProvider>)
    expect(currentTheme.mode).toBe('dark')

    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    await started
    releaseWrites()

    for (let attempt = 0; attempt < 4; attempt++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200)
        await Promise.all(writeOperations.splice(0))
      })
    }

    const stored = readUiPreferences(file).values
    expect(currentTheme.mode).toBe('dark')
    expect(window.localStorage.getItem(MODE)).toBe('dark')
    expect(stored[MODE]).toBe('dark')
    expect(Object.keys(JSON.parse(stored[BASELINE]).owners).some(owner => owner.startsWith('desktop:'))).toBe(true)
  } finally {
    releaseWrites()
    disposers.forEach(dispose => dispose())
    cleanup()
    window.localStorage.clear()
    window.sessionStorage.clear()
    Reflect.deleteProperty(window, 'hermesDesktop')
    vi.clearAllTimers()
    vi.useRealTimers()

    if (locksDescriptor) {
      Object.defineProperty(window.navigator, 'locks', locksDescriptor)
    } else {
      Reflect.deleteProperty(window.navigator, 'locks')
    }

    fs.rmSync(dir, { recursive: true, force: true })
  }
})
