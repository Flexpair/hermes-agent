import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { expect, it } from 'vitest'
import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../electron/ui-preferences'
import { captureOwnPreferences, hydrateFromSnapshot, startUiPreferencesSync } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'
import { createPluginContext } from './plugin'

it('does not overwrite an unseen peer update while its startup write is in flight', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-race-'))
  const file = path.join(dir, 'preferences.json')
  const mode = 'hermes-desktop-mode-v1'
  const profiles = 'hermes-desktop-profile-modes-v1'
  const disposers: (() => void)[] = []
  let release = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  window.localStorage.clear()
  window.sessionStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  $activeGatewayProfile.set('work')
  $gatewayState.set('open')
  await writeUiPreferences(file, { values: { [mode]: 'light', [profiles]: JSON.stringify({ work: 'light', other: 'light' }) } })
  const snapshot = readUiPreferences(file)
  captureOwnPreferences()
  hydrateFromSnapshot(snapshot)
  const stop = startUiPreferencesSync({
    snapshot, read: async () => readUiPreferences(file),
    write: async payload => { if (!payload.seed) { await gate }; return writeUiPreferences(file, parseUiPreferencesWrite(payload)) }
  })
  try {
    plugin.register(createPluginContext(plugin.id, d => disposers.push(d)))
    await new Promise(resolve => setTimeout(resolve, 250))
    await writeUiPreferences(file, { values: { [mode]: 'system', [profiles]: JSON.stringify({ work: 'light', other: 'dark' }) } })
    release()
    await new Promise(resolve => setTimeout(resolve, 500))
    expect(readUiPreferences(file).values[mode]).toBe('system')
    expect(JSON.parse(readUiPreferences(file).values[profiles]).other).toBe('dark')
  } finally {
    release()
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
