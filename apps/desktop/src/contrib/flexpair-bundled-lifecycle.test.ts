import { expect, it, vi } from 'vitest'

// Only the native bridge is substituted; SDK, context, store and glob loader are real.
it('discovers fresh defaults and preserves live disablement through restart and update reloads', async () => {
  localStorage.clear()
  vi.resetModules()
  const setPercent = vi.fn()
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: {
      zoom: { setPercent }, logLine: vi.fn(),
      onPreviewFileChanged: () => () => undefined,
      desktopPluginsRoot: async () => '/isolated-empty-plugins',
      readDir: async () => ({ entries: [] }),
      watchDirectory: async () => ({ id: 'empty-root-watch' })
    }
  })
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0))
  vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id))
  document.documentElement.dataset.hermesMode = 'dark'
  // Static trusted HTML fixture, never user content.
  document.body.innerHTML = '<section class="mb-5 grid gap-2"><div data-slot="row-button"><span class="font-semibold">MiniMax</span></div></section>'
  const ids = ['flexpair-color-palette', 'provider-card-filter']

  const boot = async () => {
    const loader = await import('./plugins')
    const store = await import('./plugins-store')
    const accent = await import('../themes/accent-override')
    loader.discoverBundledPlugins()

    return { loader, store, accent }
  }

  let app = await boot()

  for (const id of ids) {expect(app.store.$pluginRecords.get()[id]).toMatchObject({ kind: 'bundled', status: 'loaded' })}
  document.documentElement.dataset.hermesMode = 'dark'
  await vi.waitFor(() => expect(app.accent.$accentOverride.get()?.toUpperCase()).toBe('#00FFFF'))
  expect(setPercent.mock.calls).toEqual([[150]])
  expect(document.querySelector('[data-hermes-provider-filter="account"]')).not.toBeNull()
  document.documentElement.dataset.hermesMode = 'light'
  await vi.waitFor(() => expect(app.accent.$accentOverride.get()?.toUpperCase()).toBe('#157878'))
  expect(setPercent.mock.calls).toEqual([[150]])

  for (const id of ids) {await app.store.setPluginEnabled(id, false)}
  expect(app.accent.$accentOverride.get()).toBeNull()
  expect(setPercent.mock.calls).toEqual([[150], [0]])
  expect(document.querySelector('[data-hermes-provider-filter]')).toBeNull()
  expect(document.getElementById('hermes-provider-card-filter')).toBeNull()
  expect(JSON.parse(localStorage.getItem('hermes.desktop.pluginDecisions.v2')!)).toMatchObject({ 'flexpair-color-palette': false, 'provider-card-filter': false })

  // A new module graph models restart, then an updated app generation: persisted Storage remains.
  for (const generation of ['restart', 'update']) {
    vi.resetModules()
    app = await boot()

    for (const id of ids) {expect(app.store.$pluginRecords.get()[id], generation).toMatchObject({ status: 'disabled' })}
    expect(app.accent.$accentOverride.get()).toBeNull()
    expect(setPercent.mock.calls).toEqual([[150], [0]])
    expect(document.getElementById('hermes-provider-card-filter')).toBeNull()
  }

  for (const id of ids) {await app.store.setPluginEnabled(id, true)}
  expect(setPercent.mock.calls).toEqual([[150], [0], [150]])
  expect(app.accent.$accentOverride.get()?.toUpperCase()).toBe('#157878')
  expect(document.querySelector('[data-hermes-provider-filter="account"]')).not.toBeNull()

  for (const id of ids) {await app.store.setPluginEnabled(id, false)}
  document.documentElement.dataset.hermesMode = 'dark'
  await new Promise(resolve => setTimeout(resolve, 30))
  expect(app.accent.$accentOverride.get()).toBeNull()
  expect(setPercent.mock.calls).toEqual([[150], [0], [150], [0]])
  expect(document.querySelector('[data-hermes-provider-filter]')).toBeNull()
})
