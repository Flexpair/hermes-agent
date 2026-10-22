import { afterEach, expect, it, vi } from 'vitest'

import plugin from '../plugins/flexpair-color-palette/plugin'
import { $accentOverride } from '../themes/accent-override'

import { createPluginContext } from './plugin'

const disposers: (() => void)[] = []
afterEach(() => {
  disposers.splice(0).forEach(dispose => dispose())
  delete document.documentElement.dataset.hermesMode
  vi.restoreAllMocks()
})

for (const mode of ['dark', 'light', 'unknown']) {
  it(`handles ${mode} boot, transitions and default disposal without locking manual zoom`, async () => {
    const setPercent = vi.fn()
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { zoom: { setPercent } } })
    document.documentElement.dataset.hermesMode = mode
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    expect($accentOverride.get()?.toUpperCase() ?? null).toBe(mode === 'dark' ? '#00FFFF' : mode === 'light' ? '#157878' : null)
    expect(setPercent.mock.calls).toEqual([[150]])
    setPercent(125) // A user adjustment is not overwritten by mode tracking.

    for (const [next, accent] of [['dark', '#00FFFF'], ['light', '#157878'], ['light', '#157878']]) {
      document.documentElement.dataset.hermesMode = next
      await vi.waitFor(() => expect($accentOverride.get()?.toUpperCase()).toBe(accent))
    }

    expect(setPercent.mock.calls).toEqual([[150], [125]])
    disposers.splice(0).forEach(dispose => dispose())
    expect($accentOverride.get()).toBeNull()
    expect(setPercent.mock.calls).toEqual([[150], [125], [0]])
    document.documentElement.dataset.hermesMode = 'dark'
    await new Promise(resolve => setTimeout(resolve, 10))
    expect($accentOverride.get()).toBeNull()
  })
}

for (const bridge of [undefined, { zoom: { setPercent: () => { throw new Error('unavailable host') } } }]) {
  it('keeps accent lifecycle when the optional zoom bridge is missing or throws', () => {
    Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: bridge })
    document.documentElement.dataset.hermesMode = 'dark'
    expect(() => plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))).not.toThrow()
    expect($accentOverride.get()?.toUpperCase()).toBe('#00FFFF')
    disposers.splice(0).forEach(dispose => dispose())
    expect($accentOverride.get()).toBeNull()
  })
}
