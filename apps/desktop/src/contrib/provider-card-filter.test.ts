import { expect, it, vi } from 'vitest'

import plugin from '../plugins/provider-card-filter/plugin'

import { createPluginContext } from './plugin'

it('filters only exact provider/account/messenger rows and reconciles changes and disposal', async () => {
  const disposers: (() => void)[] = []
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0))
  vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id))
  // Static trusted markup exercises the reference host structures, not user HTML.
  document.body.innerHTML = `
    <input id="provider-key-DeepSeek"><input id="provider-key-OpenAI">
    <section class="mb-5 grid gap-2">
      <div id="account" data-slot="row-button"><span class="font-semibold">MiniMax</span></div>
      <div id="neutral" data-slot="row-button"><span class="font-semibold">MiniMax helper</span></div>
    </section>
    <section><aside><div class="overflow-y-auto"><ul class="space-y-1">
      <li id="messenger"><button class="row-hover"><span class="flex"><span class="truncate">DingTalk</span></span></button></li>
      <li id="allowed"><button class="row-hover"><span class="flex"><span class="truncate">Telegram</span></span></button></li>
    </ul></div></aside></section>
    <section data-tour="tab-skills"><div id="skill"><span class="font-semibold">MiniMax</span></div></section>
    <p id="chat">MiniMax DingTalk DeepSeek</p>`
  const account = document.getElementById('account')!
  const messenger = document.getElementById('messenger')!
  const marker = 'data-hermes-provider-filter'

  try {
    plugin.register(createPluginContext(plugin.id, dispose => disposers.push(dispose)))
    expect(getComputedStyle(document.getElementById('provider-key-DeepSeek')!).display).toBe('none')
    expect(getComputedStyle(document.getElementById('provider-key-OpenAI')!).display).not.toBe('none')
    expect(account.getAttribute(marker)).toBe('account')
    expect(messenger.getAttribute(marker)).toBe('messenger')

    for (const id of ['neutral', 'allowed', 'skill', 'chat']) {expect(document.getElementById(id)!.hasAttribute(marker)).toBe(false)}
    account.querySelector('span')!.textContent = 'OpenAI'
    messenger.querySelector('span.truncate')!.textContent = 'Telegram'
    await vi.waitFor(() => {
      expect(account.hasAttribute(marker)).toBe(false)
      expect(messenger.hasAttribute(marker)).toBe(false)
    })
    account.querySelector('span')!.textContent = 'Qwen Code'
    messenger.querySelector('span.truncate')!.textContent = 'QQ Bot'
    await vi.waitFor(() => {
      expect(account.getAttribute(marker)).toBe('account')
      expect(messenger.getAttribute(marker)).toBe('messenger')
    })
    account.remove()
    await vi.waitFor(() => expect(account.hasAttribute(marker)).toBe(false))
    document.querySelector('section.mb-5')!.append(account)
    await vi.waitFor(() => expect(account.hasAttribute(marker)).toBe(true))
    disposers.splice(0).forEach(dispose => dispose())
    expect(document.getElementById('hermes-provider-card-filter')).toBeNull()
    expect(document.querySelector(`[${marker}]`)).toBeNull()
    account.querySelector('span')!.textContent = 'MiniMax'
    await new Promise(resolve => setTimeout(resolve, 30))
    expect(account.hasAttribute(marker)).toBe(false)
  } finally {
    disposers.forEach(dispose => dispose())
    document.body.replaceChildren()
    vi.unstubAllGlobals()
  }
})
