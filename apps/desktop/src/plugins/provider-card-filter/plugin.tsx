import type { HermesPlugin } from '@hermes/plugin-sdk';

// Private presentation-only customization, not a catalog-admissible SDK plugin.
// List rows lack stable entry-ID hooks; this narrowly scoped DOM overlay can
// require maintenance after Desktop updates. No credentials or routing changes.
const css = "/* Presentation only: no credential or model-routing changes. */\n[id=\"provider-key-Qwen-Cloud\"],\n[id=\"provider-key-Xiaomi-MiMo\"],\n[id=\"provider-key-Tencent-TokenHub\"],\n[id=\"provider-key-Tencent-TokenPlan\"],\n[id=\"provider-key-DeepSeek\"],\n[id=\"provider-key-Z-AI-GLM-\"],\n[id=\"provider-key-Kimi-Kimi-Coding-Plan\"],\n[id=\"provider-key-Kimi-Moonshot-China-\"],\n[id=\"provider-key-StepFun-Step-Plan\"],\n[id=\"provider-key-MiniMax\"],\n[id=\"provider-key-MiniMax-China-\"],\n[id=\"provider-key-Alibaba-Cloud-DashScope-China-\"],\n[id=\"provider-key-Alibaba-Cloud-Token-Plan-\"],\n[id=\"provider-key-Alibaba-Cloud-Token-Plan-China-\"],\n[id=\"provider-key-Alibaba-Cloud-Coding-Plan-\"],\n[id=\"provider-key-Alibaba-Cloud-Coding-Plan-China-\"] {\n  display: none !important;\n}\n";
const accountTitles = new Set(['MiniMax', 'Qwen Code']);

const messengerTitles = new Set([
  'DingTalk', 'Feishu / Lark', 'WeCom (group bot)', 'WeCom (app)',
  'Weixin / WeChat (Personal)', 'QQ Bot', 'Yuanbao (元宝)'
]);

// Match only account-row title spans, never general page text or inputs.
const rowSelector = 'section.mb-5.grid.gap-2 > [data-slot="row-button"], section.mb-5.grid.gap-2 > div.group.grid';
const marker = 'data-hermes-provider-filter';

const plugin: HermesPlugin = {
  id: 'provider-card-filter',
  name: 'Provider Card Filter',
  description: 'Hide selected Chinese-company provider, account and messenger list entries. Skill activation states and controls remain visible. Credentials, model routing and the color palette are unchanged.',
  defaultEnabled: true,
  register(ctx) {
    const style = document.createElement('style');
    style.id = 'hermes-provider-card-filter';
    style.textContent = css + '\n[data-hermes-provider-filter="account"], [data-hermes-provider-filter="messenger"] { display: none !important; }';
    document.body.appendChild(style);
    const marked = new Map<Element, string>();
    let lastCount = -1;

    const update = () => {
      const next = new Map<Element, string>();

      for (const row of document.querySelectorAll(rowSelector)) {
        const title = row.querySelector('[data-slot="row-button"] span.font-semibold, span.font-semibold');

        if (title && accountTitles.has((title.textContent ?? '').trim())) {next.set(row, 'account');}
      }

      // PlatformRow has no platform-ID attribute. Hide the li, not its parents.
      for (const row of document.querySelectorAll('section aside > div.overflow-y-auto > ul.space-y-1 > li')) {
        const title = row.querySelector(':scope > button.row-hover > span.flex > span.truncate');

        if (title && messengerTitles.has((title.textContent ?? '').trim())) {next.set(row, 'messenger');}
      }

      for (const [row] of marked) {
        if (!next.has(row)) {row.removeAttribute(marker);}
      }

      for (const [row, kind] of next) {
        if (marked.get(row) !== kind) {row.setAttribute(marker, kind);}
      }

      marked.clear();

      for (const [row, kind] of next) {marked.set(row, kind);}

      if (next.size !== lastCount) {
        lastCount = next.size;
        (window as Window & { hermesDesktop?: { logLine?: (line: string) => void } }).hermesDesktop?.logLine?.('[provider-card-filter] rows-hidden=' + next.size);
      }
    };

    // Re-scan at most once per animation frame: chat streaming and other frequent
    // mutations must not trigger a full document scan per change.
    let pending = 0;

    const schedule = () => {
      if (!pending) {pending = requestAnimationFrame(() => {
        pending = 0;
        update();
      });}
    };

    const observer = new MutationObserver(schedule);
    ctx.onDispose(() => {
      observer.disconnect();

      if (pending) {
        cancelAnimationFrame(pending);
        pending = 0;
      }

      for (const [row] of marked) {row.removeAttribute(marker);}
      marked.clear();
      style.remove();
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['class', 'data-active'] });
    update();
    (window as Window & { hermesDesktop?: { logLine?: (line: string) => void } }).hermesDesktop?.logLine?.('[provider-card-filter] enabled; accounts=' + accountTitles.size + '; messengers=' + messengerTitles.size);
  }
};

export default plugin;
