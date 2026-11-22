import { spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

import { expect, it } from 'vitest'

import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../electron/ui-preferences'
import { captureOwnPreferences, hydrateFromSnapshot, startUiPreferencesSync } from '../lib/ui-preferences/sync'
import plugin from '../plugins/flexpair-color-palette/plugin'
import { $activeGatewayProfile } from '../store/profile'
import { $gatewayState } from '../store/session'

import { createPluginContext } from './plugin'

const MODE = 'hermes-desktop-mode-v1'
const PROFILES = 'hermes-desktop-profile-modes-v1'
const ZOOM = 'hermes.desktop.zoom'

async function until(check: () => boolean) {
  const deadline = Date.now() + 5000
  while (!check()) {
    if (Date.now() > deadline) throw new Error('timed out waiting for preference writer')
    await new Promise(resolve => setTimeout(resolve, 10))
  }
}

it('rebases a startup write blocked by a real peer holding the store lock', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-inflight-'))
  const file = path.join(dir, 'preferences.json')
  const ready = path.join(dir, 'ready')
  const release = path.join(dir, 'release')
  const disposers: (() => void)[] = []
  let stop = () => {}
  window.localStorage.clear()
  window.sessionStorage.clear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: undefined })
  $activeGatewayProfile.set('work')
  $gatewayState.set('open')
  await writeUiPreferences(file, { values: { [MODE]: 'light', [PROFILES]: JSON.stringify({ work: 'light', other: 'light' }), [ZOOM]: '125' } })
  const snapshot = readUiPreferences(file)
  captureOwnPreferences()
  hydrateFromSnapshot(snapshot)

  // The child pauses inside the real writer's locked read. This guarantees the
  // startup write is already in flight while another process changes the file.
  const peerScript = `
    import fs from 'node:fs';
    const [moduleUrl, file, ready, release] = process.argv.slice(1);
    const { writeUiPreferences } = await import(moduleUrl);
    const read = fs.readFileSync;
    fs.readFileSync = function (name, ...args) {
      if (name === file && !fs.existsSync(ready)) {
        fs.writeFileSync(ready, 'locked');
        while (!fs.existsSync(release)) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
      }
      return read.call(this, name, ...args);
    };
    await writeUiPreferences(file, { values: {
      '${MODE}': 'system', '${PROFILES}': JSON.stringify({ work: 'light', other: 'dark' }), '${ZOOM}': '140'
    }});
  `
  const moduleUrl = pathToFileURL(path.resolve('electron/ui-preferences.ts')).href
  const child = spawn(process.execPath, ['--experimental-strip-types', '--input-type=module', '-e', peerScript, moduleUrl, file, ready, release], { stdio: ['ignore', 'ignore', 'pipe'] })
  let childError = ''
  child.stderr.on('data', chunk => { childError += String(chunk) })
  const exited = new Promise<number | null>(resolve => child.on('exit', resolve))
  let attempted = false
  try {
    await until(() => fs.existsSync(ready) || child.exitCode !== null)
    expect(child.exitCode, childError).toBeNull()
    stop = startUiPreferencesSync({
      snapshot,
      read: async () => readUiPreferences(file),
      write: payload => {
        if (!payload.seed) attempted = true
        return writeUiPreferences(file, parseUiPreferencesWrite(payload))
      }
    })
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    await until(() => attempted)
    fs.writeFileSync(release, 'go')
    expect(await exited, childError).toBe(0)
    await until(() => {
      const values = readUiPreferences(file).values
      return values[MODE] === 'system' && JSON.parse(values[PROFILES]).work === 'dark' && JSON.parse(values[PROFILES]).other === 'dark'
    })
    expect(readUiPreferences(file).values[ZOOM]).toBe('140')
    expect(window.localStorage.getItem(MODE)).toBe('system')
  } finally {
    fs.writeFileSync(release, 'go')
    await exited
    stop()
    disposers.forEach(dispose => dispose())
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
}, 15_000)
