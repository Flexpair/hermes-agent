import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { expect, it, vi } from 'vitest'

import { parseUiPreferencesWrite, readUiPreferences, writeUiPreferences } from '../../../electron/ui-preferences'

type UiPreferences = NonNullable<typeof window.hermesDesktop>['uiPreferences']

async function withBridge<T>(
  file: string,
  overrides: Partial<UiPreferences>,
  run: () => Promise<T>
): Promise<T> {
  const descriptor = Object.getOwnPropertyDescriptor(window, 'hermesDesktop')
  const previous = window.hermesDesktop

  const uiPreferences: UiPreferences = {
    snapshot: readUiPreferences(file),
    read: async () => readUiPreferences(file),
    write: async payload => writeUiPreferences(file, parseUiPreferencesWrite(payload)),
    ...overrides
  }

  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true, value: { ...previous, uiPreferences }
  })

  try {
    return await run()
  } finally {
    if (descriptor) { Object.defineProperty(window, 'hermesDesktop', descriptor) }
    else { Reflect.deleteProperty(window, 'hermesDesktop') }
  }
}

it('does not seed old default keybinds before stores classify them as provisional', async () => {
  vi.useFakeTimers()
  vi.resetModules()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-early-seed-'))
  const file = path.join(dir, 'prefs.json')
  const key = 'hermes.desktop.keybinds'
  window.localStorage.setItem(key, '{}')

  try {
    await withBridge(file, {}, async () => {
      const { bootRenderer } = await import('./boot')
      await bootRenderer(async () => {
        // Module loading can yield before keybinds evaluates.
        await vi.advanceTimersByTimeAsync(100)
        await import('@/store/keybinds')
      })
      await vi.advanceTimersByTimeAsync(500)
      expect(readUiPreferences(file).values[key]).toBeUndefined()
    })
  } finally {
    vi.useRealTimers()
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it('queues startup writes and incoming changes until the app graph has loaded', async () => {
  vi.useFakeTimers()
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

  try {
    await withBridge(file, {
      write,
      onChanged: listener => { notify = listener;

 return () => undefined }
    }, async () => {
      const { bootRenderer } = await import('./boot')
      await bootRenderer(async () => {
        const { readKey, writeKey } = await import('../storage')
        readKey(profiles)
        writeKey(profiles, '{"work":"dark","peer":"light"}')
        writeKey(mode, 'dark')
        const peer = await writeUiPreferences(file, { values: { [profiles]: '{"work":"light","peer":"dark"}' } })
        notify(peer)
        await vi.advanceTimersByTimeAsync(50)
        expect(window.localStorage.getItem(profiles)).toBe('{"work":"dark","peer":"light"}')
        expect(write).not.toHaveBeenCalled()
      })
      await vi.advanceTimersByTimeAsync(500)
      await Promise.all(write.mock.results.map(result => result.value))
      expect(readUiPreferences(file).values[mode]).toBe('dark')
      expect(JSON.parse(readUiPreferences(file).values[profiles])).toEqual({ work: 'dark', peer: 'dark' })
    })
  } finally {
    vi.useRealTimers()
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

it('stops listening without contacting the store if app loading fails', async () => {
  vi.useFakeTimers()
  vi.resetModules()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flexpair-failed-boot-'))
  const file = path.join(dir, 'prefs.json')
  const read = vi.fn(async () => readUiPreferences(file))

  const write = vi.fn(async (payload: Parameters<typeof parseUiPreferencesWrite>[0]) =>
    writeUiPreferences(file, parseUiPreferencesWrite(payload)))

  const unsubscribe = vi.fn()

  try {
    await withBridge(file, { read, write, onChanged: () => unsubscribe }, async () => {
      const { bootRenderer } = await import('./boot')
      await expect(bootRenderer(async () => {
        const { writeKey } = await import('../storage')
        writeKey('hermes-desktop-mode-v1', 'dark')
        throw new Error('load failed')
      })).rejects.toThrow('load failed')
      await vi.advanceTimersByTimeAsync(200)
      expect(unsubscribe).toHaveBeenCalledOnce()
      expect(read).not.toHaveBeenCalled()
      expect(write).not.toHaveBeenCalled()
    })
  } finally {
    vi.useRealTimers()
    window.localStorage.clear()
    window.sessionStorage.clear()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
