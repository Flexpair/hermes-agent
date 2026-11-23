import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { writeKey } from '../lib/storage'
import { bootRenderer } from '../lib/ui-preferences/boot'
import type { UiPreferencesBridge, UiPreferencesSnapshot } from '../lib/ui-preferences/sync'
import { hydrateFromSnapshot, startUiPreferencesSync } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const MODE_KEY = 'hermes-desktop-mode-v1'
const JOINED_KEY = 'hermes:ui-preferences:generation'
const SIDEBAR_KEY = 'hermes.desktop.sidebarShowAllSessions'
const disposers: (() => void)[] = []

let stopSync = () => {}

function machineStore() {
  let current: UiPreferencesSnapshot = {
    exists: true,
    generation: 'g1',
    revision: 1,
    values: { [MODE_KEY]: 'light' }
  }

  const listeners = new Set<(snapshot: UiPreferencesSnapshot) => void>()
  const notify = () => listeners.forEach(listener => listener(current))

  const bridge: UiPreferencesBridge = {
    snapshot: current,
    read: async () => current,
    write: async payload => {
      const values = { ...current.values }

      for (const [key, value] of Object.entries(payload.values)) {
        if (value === null) {
          delete values[key]
        } else {
          values[key] = value
        }
      }

      current = { ...current, revision: current.revision + 1, values }
      notify()

      return current
    },
    onChanged: callback => {
      listeners.add(callback)

      return () => listeners.delete(callback)
    }
  }

  return {
    bridge,
    snapshot: () => current,
    external: (values: Record<string, string>) => {
      current = { ...current, revision: current.revision + 1, values }
      notify()
    }
  }
}

afterEach(() => {
  stopSync()

  stopSync = () => {}
  act(() => cleanup())
  act(() => { disposers.splice(0).forEach(dispose => dispose()) })
  vi.useRealTimers()
  window.localStorage.clear()
  window.sessionStorage.clear()
  Reflect.deleteProperty(window, 'hermesDesktop')
})

it('keeps the palette mode when a shared preference write triggers snapshot adoption', async () => {
  vi.useFakeTimers()
  window.localStorage.clear()
  window.localStorage.setItem(JOINED_KEY, 'g1')
  const store = machineStore()
  hydrateFromSnapshot(store.snapshot())
  stopSync = startUiPreferencesSync(store.bridge)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))

  writeKey(SIDEBAR_KEY, 'true')

  await act(async () => { await vi.advanceTimersByTimeAsync(500) })

  expect(window.localStorage.getItem(MODE_KEY)).toBe('dark')
})

it('starts sync after boot hydration but before bundled plugin registration', async () => {
  vi.useFakeTimers()
  window.localStorage.setItem(JOINED_KEY, 'g1')
  const store = machineStore()
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: { uiPreferences: store.bridge }
  })

  await bootRenderer(async () => {
    stopSync = startUiPreferencesSync(store.bridge)
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    writeKey(SIDEBAR_KEY, 'true')
  })

  await act(async () => { await vi.advanceTimersByTimeAsync(500) })

  expect(window.localStorage.getItem(MODE_KEY)).toBe('dark')
  expect(store.snapshot().values[MODE_KEY]).toBe('dark')
})

it('keeps the plugin mode when the host publishes a light snapshot', async () => {
  vi.useFakeTimers()
  window.localStorage.setItem(JOINED_KEY, 'g1')
  const store = machineStore()
  hydrateFromSnapshot(store.snapshot())
  stopSync = startUiPreferencesSync(store.bridge)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))

  store.external({ [MODE_KEY]: 'light' })

  await act(async () => { await vi.advanceTimersByTimeAsync(500) })

  expect(window.localStorage.getItem(MODE_KEY)).toBe('dark')
  expect(store.snapshot().values[MODE_KEY]).toBe('dark')
})

it('lets a manual light-mode choice replace the plugin mode in the host store', async () => {
  vi.useFakeTimers()
  window.localStorage.setItem(JOINED_KEY, 'g1')
  const store = machineStore()
  hydrateFromSnapshot(store.snapshot())
  stopSync = startUiPreferencesSync(store.bridge)
  plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
  let theme!: ReturnType<typeof useTheme>

  function Probe() {
    theme = useTheme()

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)
  act(() => theme.setMode('light'))
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })

  expect(window.localStorage.getItem(MODE_KEY)).toBe('light')
  expect(store.snapshot().values[MODE_KEY]).toBe('light')
})
