import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { expect, it, vi } from 'vitest'
import { readUiPreferences, writeUiPreferences, parseUiPreferencesWrite } from '../../../electron/ui-preferences'

it('does not seed old default keybinds before stores classify them as provisional', async () => {
  vi.resetModules()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-early-seed-'))
  const file = path.join(dir, 'prefs.json')
  const key = 'hermes.desktop.keybinds'
  window.localStorage.setItem(key, '{}')
  window.hermesDesktop = { uiPreferences: {
    snapshot: readUiPreferences(file),
    read: async () => readUiPreferences(file),
    write: async (payload: Parameters<typeof parseUiPreferencesWrite>[0]) =>
      writeUiPreferences(file, parseUiPreferencesWrite(payload))
  } } as unknown as typeof window.hermesDesktop
  try {
    const { bootRenderer } = await import('./boot')
    await bootRenderer(async () => {
      // Module loading can yield before keybinds evaluates.
      await new Promise(resolve => setTimeout(resolve, 100))
      await import('@/store/keybinds')
    })
    await new Promise(resolve => setTimeout(resolve, 500))
    expect(readUiPreferences(file).values[key]).toBeUndefined()
  } finally {
    Reflect.deleteProperty(window, 'hermesDesktop')
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it('queues startup writes and incoming changes until the app graph has loaded', async () => {
  vi.resetModules()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-startup-writes-'))
  const file = path.join(dir, 'prefs.json')
  const mode = 'hermes-desktop-mode-v1'
  const profiles = 'hermes-desktop-profile-modes-v1'
  await writeUiPreferences(file, { values: { [mode]: 'light', [profiles]: '{"work":"light","peer":"light"}' } })
  let notify: (snapshot: ReturnType<typeof readUiPreferences>) => void = () => undefined
  const write = vi.fn(async (payload: Parameters<typeof parseUiPreferencesWrite>[0]) =>
    writeUiPreferences(file, parseUiPreferencesWrite(payload)))
  window.hermesDesktop = { uiPreferences: {
    snapshot: readUiPreferences(file),
    read: async () => readUiPreferences(file),
    write,
    onChanged: (listener: typeof notify) => { notify = listener; return () => undefined }
  } } as unknown as typeof window.hermesDesktop

  try {
    const { bootRenderer } = await import('./boot')
    await bootRenderer(async () => {
      const { readKey, writeKey } = await import('../storage')
      readKey(profiles)
      writeKey(profiles, '{"work":"dark","peer":"light"}')
      writeKey(mode, 'dark')
      const peer = await writeUiPreferences(file, { values: { [profiles]: '{"work":"light","peer":"dark"}' } })
      notify(peer)
      await new Promise(resolve => setTimeout(resolve, 50))
      expect(window.localStorage.getItem(profiles)).toBe('{"work":"dark","peer":"light"}')
      expect(write).not.toHaveBeenCalled()
    })
    await new Promise(resolve => setTimeout(resolve, 500))
    expect(readUiPreferences(file).values[mode]).toBe('dark')
    expect(JSON.parse(readUiPreferences(file).values[profiles])).toEqual({ work: 'dark', peer: 'dark' })
  } finally {
    Reflect.deleteProperty(window, 'hermesDesktop')
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it('stops listening without contacting the store if app loading fails', async () => {
  vi.resetModules()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-failed-boot-'))
  const file = path.join(dir, 'prefs.json')
  const read = vi.fn(async () => readUiPreferences(file))
  const write = vi.fn(async (payload: Parameters<typeof parseUiPreferencesWrite>[0]) =>
    writeUiPreferences(file, parseUiPreferencesWrite(payload)))
  const unsubscribe = vi.fn()
  window.hermesDesktop = { uiPreferences: {
    snapshot: readUiPreferences(file), read, write, onChanged: () => unsubscribe
  } } as unknown as typeof window.hermesDesktop

  try {
    const { bootRenderer } = await import('./boot')
    await expect(bootRenderer(async () => {
      const { writeKey } = await import('../storage')
      writeKey('hermes-desktop-mode-v1', 'dark')
      throw new Error('load failed')
    })).rejects.toThrow('load failed')
    await new Promise(resolve => setTimeout(resolve, 200))
    expect(unsubscribe).toHaveBeenCalledOnce()
    expect(read).not.toHaveBeenCalled()
    expect(write).not.toHaveBeenCalled()
  } finally {
    Reflect.deleteProperty(window, 'hermesDesktop')
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
