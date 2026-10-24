import fs from 'node:fs'
import path from 'node:path'

import { writeEnvFile, writeMockProviderConfig } from '../../../tests-js/scripts/mock-provider-config'
import { startMockServer } from '../../../tests-js/scripts/mock-server'

import { buildAppEnv, createSandbox, launchDesktop } from './fixtures'
import { collectErrorBanners, type ElectronApplication, expect, type Page, test } from './test'

// Fork-owned acceptance: real production dist, normal bundled loader and native zoom.
test('Flexpair palette startup and manual preferences', async () => {
  test.setTimeout(120_000)
  const sandbox = createSandbox('flexpair-palette')
  const mock = await startMockServer()
  writeMockProviderConfig(sandbox.hermesHome, mock.url)
  writeEnvFile(sandbox.hermesHome, 'e2e-mock-key', mock.url)
  fs.unlinkSync(path.join(sandbox.userDataDir, 'zoom-state.json'))
  const env = buildAppEnv(sandbox)
  delete env.HERMES_DESKTOP_DEV_SERVER
  let app: ElectronApplication | undefined
  let page: Page
  const zoom = () => app!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getZoomFactor())

  const mode = () => page.evaluate(() => ({
    mode: document.documentElement.dataset.hermesMode,
    colorScheme: getComputedStyle(document.documentElement).colorScheme,
    background: getComputedStyle(document.body).backgroundColor,
  }))

  try {
    console.log('SANDBOX', sandbox.root)
    ;({ app, page } = await launchDesktop(env))
    await expect.poll(zoom).toBeCloseTo(1.5, 5)
    await expect.poll(async () => (await mode()).mode).toBe('dark')
    console.log('STARTUP', await mode(), await zoom(), page.url())
    await page.getByRole('button', { name: 'Open settings', exact: true }).click()
    await page.getByRole('button', { name: /^(Appearance|Darstellung)$/ }).click()
    await page.getByRole('button', { name: /^(Theme|Design)$/ }).click()
    await page.getByRole('button', { name: /^(Light|Hell)$/ }).click()
    await expect.poll(async () => (await mode()).mode).toBe('light')
    await expect.poll(async () => (await mode()).colorScheme).toBe('light')
    // Same native preload capability used by Appearance's scale control.
    await page.evaluate(() => {
      const desktopWindow = window as Window & { hermesDesktop?: { zoom: { setPercent(percent: number): void } } }
      desktopWindow.hermesDesktop!.zoom.setPercent(125)
    })
    await expect.poll(zoom).toBeCloseTo(1.25, 5)
    await page.waitForTimeout(1500)
    expect(await zoom()).toBeCloseTo(1.25, 5)
    expect((await mode()).mode).toBe('light')
    console.log('MANUAL', await mode(), await zoom())
    await expect.poll(() => JSON.parse(fs.readFileSync(path.join(sandbox.userDataDir, 'zoom-state.json'), 'utf8')).zoomLevel).toBeCloseTo(Math.log(1.25) / Math.log(1.2), 5)
    console.log('PERSISTED_ZOOM', fs.readFileSync(path.join(sandbox.userDataDir, 'zoom-state.json'), 'utf8'))
    await page.reload()
    await expect.poll(zoom).toBeCloseTo(1.5, 5)
    await expect.poll(async () => (await mode()).mode).toBe('dark')
    await expect.poll(async () => (await mode()).colorScheme).toBe('dark')
    console.log('RELOAD', await mode(), await zoom())
    // Activation lives in Capabilities; Settings only contains plugin options.
    await page.goto(page.url().split('#')[0] + '#/capabilities?tab=plugins')
    const paletteSwitch = page.getByRole('switch', { name: /: Flexpair Color Palette$/ })
    await expect(paletteSwitch).toBeChecked()
    await paletteSwitch.click()
    await expect(paletteSwitch).not.toBeChecked()
    await expect.poll(async () => (await mode()).mode).toBe('light')
    await expect.poll(async () => (await mode()).colorScheme).toBe('light')
    console.log('DISABLED_RESTORED_LIGHT', await mode(), await zoom())
    await paletteSwitch.click()
    await expect(paletteSwitch).toBeChecked()
    await expect.poll(async () => (await mode()).mode).toBe('dark')
    await expect.poll(zoom).toBeCloseTo(1.5, 5)
    expect(await collectErrorBanners(page)).toEqual([])
    await app.close()
    ;({ app, page } = await launchDesktop(env))
    await expect.poll(zoom).toBeCloseTo(1.5, 5)
    await expect.poll(async () => (await mode()).mode).toBe('dark')
    console.log('RESTART', await mode(), await zoom())
    await page.goto(page.url().split('#')[0] + '#/settings')
    await page.getByRole('button', { name: /^(Providers|Anbieter)$/ }).click()
    await page.getByRole('button', { name: /^(Accounts|Konten)$/ }).click()
    await page.getByRole('button', { name: /^(Other providers|Weitere Provider)$/ }).click()
    const account = page.locator('[data-hermes-provider-filter="account"]')
    await expect.poll(() => account.count()).toBeGreaterThan(0)

    for (const row of await account.all()) {
      await expect(row).toBeHidden()
    }

    console.log('FILTER_ACCOUNTS', await account.allTextContents())
    await page.getByRole('button', { name: /^(API keys|API Keys|API-Schlüssel)$/ }).click()
    await expect(page.locator('[id="provider-key-DeepSeek"]')).toBeAttached()
    await expect(page.locator('[id="provider-key-DeepSeek"]')).toBeHidden()
    await expect(page.locator('[id="provider-key-OpenAI-API"]')).toBeVisible()
    console.log('FILTER_PROVIDERS', 'DeepSeek hidden; OpenAI visible')
    await page.goto(page.url().split('#')[0] + '#/messaging')
    const messenger = page.locator('[data-hermes-provider-filter="messenger"]')
    await expect.poll(() => messenger.count()).toBeGreaterThan(0)

    for (const row of await messenger.all()) {
      await expect(row).toBeHidden()
    }

    console.log('FILTER_MESSENGERS', await messenger.allTextContents())
    expect(await collectErrorBanners(page)).toEqual([])
  } finally {
    await app?.close().catch(() => undefined)
    await mock.close()
    sandbox.cleanup()
  }
})
