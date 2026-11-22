import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { act, cleanup, render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../electron/ui-preferences'
import { captureOwnPreferences, getPreferenceClaim, hydrateFromSnapshot, startUiPreferencesSync } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'
import { ThemeProvider, useTheme } from '../themes/context'

import { createPluginContext } from './plugin'

const MODE = 'hermes-desktop-mode-v1'

async function setupProbe(initialMode: null | string, desktopBridge: boolean) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-native-store-probe-'))
  const file = path.join(dir, 'ui-preferences.json')
  const disposers: (() => void)[] = []
  const writeOperations: Promise<ReturnType<typeof readUiPreferences>>[] = []
  const setPercent = vi.fn()
  const setNativeTheme = vi.fn()

  window.localStorage.clear()
  window.sessionStorage.clear()
  vi.useFakeTimers()
  $activeGatewayProfile.set('default')
  $gatewayState.set('open')

  if (initialMode !== null) {
    await writeUiPreferences(file, { values: { [MODE]: initialMode } })
  }

  const snapshot = readUiPreferences(file)
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: desktopBridge ? { zoom: { setPercent }, setNativeTheme } : undefined
  })
  captureOwnPreferences()
  hydrateFromSnapshot(snapshot)

  const stop = startUiPreferencesSync({
    snapshot,
    read: async () => readUiPreferences(file),
    write: payload => {
      const operation = writeUiPreferences(file, parseUiPreferencesWrite(payload))
      writeOperations.push(operation)

      return operation
    }
  }, undefined, getPreferenceClaim)

  return {
    file,
    setNativeTheme,
    setPercent,
    register: () => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose))),
    settle: async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(500)
          await Promise.all(writeOperations.splice(0))
        })
      }
    },
    cleanup: () => {
      cleanup()
      stop()
      disposers.forEach(dispose => dispose())
      window.localStorage.clear()
      window.sessionStorage.clear()
      Reflect.deleteProperty(window, 'hermesDesktop')
      vi.clearAllTimers()
      vi.useRealTimers()
      fs.rmSync(dir, { recursive: true, force: true })
    }
  }
}

function mountTheme() {
  let theme!: ReturnType<typeof useTheme>

  function Probe() {
    theme = useTheme()

    return null
  }

  render(<ThemeProvider><Probe /></ThemeProvider>)

  return () => theme
}

it.each([false, true])('native stored light survives plugin boot and reapplies on sync (native pin=%s)', async nativePin => {
  const probe = await setupProbe('light', true)

  try {
    probe.register()

    if (nativePin) {
      window.hermesDesktop?.setNativeTheme?.('dark')
    }

    expect(window.localStorage.getItem(MODE)).toBe('dark')
    const theme = mountTheme()
    await probe.settle()

    expect(theme().mode).toBe('dark')
    expect(readUiPreferences(probe.file).values[MODE]).toBe('dark')
  } finally {
    probe.cleanup()
  }
})

it.each([['absent', null], ['light', 'light']] as const)('checks startup against a %s native preference', async (_label, initialMode) => {
  const probe = await setupProbe(initialMode, true)

  try {
    probe.register()
    const theme = mountTheme()
    await probe.settle()

    expect(theme().mode).toBe('dark')
    expect(readUiPreferences(probe.file).values[MODE]).toBe('dark')
  } finally {
    probe.cleanup()
  }
})

it('persists the plugin startup without a native desktop bridge', async () => {
  const probe = await setupProbe('light', false)

  try {
    const theme = mountTheme()
    await probe.settle()
    act(() => probe.register())
    await probe.settle()

    expect(theme().mode).toBe('dark')
    expect(readUiPreferences(probe.file).values[MODE]).toBe('dark')
  } finally {
    probe.cleanup()
  }
})
