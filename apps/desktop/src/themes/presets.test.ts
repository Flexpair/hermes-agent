import { describe, expect, it } from 'vitest'

import {
  BUILTIN_THEME_LIST,
  BUILTIN_THEMES,
  DEFAULT_SKIN_NAME,
  DEFAULT_TYPOGRAPHY,
  EMOJI_FALLBACK,
  nousAltTheme
} from './presets'

// Flexpair-specific default and palette contracts remain covered beside
// upstream's typography regression cases.
describe('theme typography Latin Extended fallback (#61392)', () => {
  const monoStacks: Array<[string, string]> = [
    ['DEFAULT_TYPOGRAPHY.fontMono', DEFAULT_TYPOGRAPHY.fontMono],
    ...BUILTIN_THEME_LIST.map(theme => [
      `${theme.name}.effectiveFontMono`,
      theme.typography?.fontMono
        ? `${theme.typography.fontMono}, ${DEFAULT_TYPOGRAPHY.fontMono}`
        : DEFAULT_TYPOGRAPHY.fontMono
    ] as [string, string])
  ]

  it.each(monoStacks)('%s falls back to bundled JetBrains Mono before generic fonts', (_label, stack) => {
    const jetbrains = stack.indexOf('JetBrains Mono')
    const genericIndexes = ['ui-monospace', 'monospace', 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji']
      .map(font => stack.indexOf(font))
      .filter(index => index >= 0)

    expect(jetbrains).toBeGreaterThanOrEqual(0)
    expect(genericIndexes.length).toBeGreaterThan(0)
    expect(jetbrains).toBeLessThan(Math.min(...genericIndexes))
  })

  it('default stack includes common Linux monospace glyph fallbacks', () => {
    expect(DEFAULT_TYPOGRAPHY.fontMono).toContain('DejaVu Sans Mono')
    expect(DEFAULT_TYPOGRAPHY.fontMono).toContain('Liberation Mono')
    expect(DEFAULT_TYPOGRAPHY.fontMono).toContain('Noto Sans Mono')
  })
})

// #40364: none of the UI text/mono fonts carry emoji glyphs, so every font
// stack must end with a color-emoji fallback or emoji render as tofu on
// platforms whose default font lacks them (e.g. Linux).
describe('theme typography emoji fallback (#40364)', () => {
  const stacks: Array<[string, string]> = [
    ['DEFAULT_TYPOGRAPHY.fontSans', DEFAULT_TYPOGRAPHY.fontSans],
    ['DEFAULT_TYPOGRAPHY.fontMono', DEFAULT_TYPOGRAPHY.fontMono],
    // A theme may override only fontMono (fontSans then falls back to the
    // default, which already carries the emoji stack), so skip undefined.
    ...BUILTIN_THEME_LIST.flatMap(theme =>
      (
        [
          [`${theme.name}.fontSans`, theme.typography?.fontSans],
          [`${theme.name}.fontMono`, theme.typography?.fontMono]
        ] as Array<[string, string | undefined]>
      ).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    )
  ]

  it.each(stacks)('%s includes a color-emoji font', (_label, stack) => {
    expect(stack).toMatch(/Apple Color Emoji|Segoe UI Emoji|Noto Color Emoji|(^|,\s*)emoji\b/)
  })

  it('EMOJI_FALLBACK lists the major platform emoji fonts', () => {
    expect(EMOJI_FALLBACK).toContain('Apple Color Emoji')
    expect(EMOJI_FALLBACK).toContain('Segoe UI Emoji')
    expect(EMOJI_FALLBACK).toContain('Noto Color Emoji')
  })
})

// The pre-GitHub Nous palette stays available as nous-alt; nous is still
// GitHub chrome + brand blue (the Flexpair fork defaults to flexpair-dark).
describe('nous-alt is the retired Nous, not the default', () => {
  it('is registered under its own name, apart from nous', () => {
    expect(DEFAULT_SKIN_NAME).toBe('flexpair-dark')
    expect(BUILTIN_THEMES['nous-alt']).toBe(nousAltTheme)
    expect(BUILTIN_THEMES.nous).not.toBe(nousAltTheme)
    expect(nousAltTheme.darkColors?.background).toBe('#0D2F86')
    expect(BUILTIN_THEMES.nous.darkColors?.background).not.toBe(nousAltTheme.darkColors?.background)
  })
})

// Flexpair fork: company themes are built in, flexpair-dark is the default, and
// every palette color is white, black, cyan (or a darkening) or a #157878 step.
describe('flexpair themes', () => {
  const onLine = (hex: string, base: [number, number, number]) => {
    const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16))

    return [0, 255].some(end => {
      for (let k = 0; k <= 1000; k++) {
        const p = base.map(b => b + (end - b) * (k / 1000))

        if (p.every((v, i) => Math.abs(v - c[i]) <= 2)) {
          return true
        }
      }

      return false
    })
  }

  it('flexpair-dark is the default skin', () => {
    expect(DEFAULT_SKIN_NAME).toBe('flexpair-dark')
    expect(BUILTIN_THEMES[DEFAULT_SKIN_NAME]).toBeDefined()
    expect(BUILTIN_THEMES['flexpair-light']).toBeDefined()
  })

  it('uses a contrasting composer ring in the light palette', () => {
    expect(BUILTIN_THEMES['flexpair-light'].colors.composerRing).toBe('#157878')
  })

  it.each(['flexpair-dark', 'flexpair-light'])('%s only uses the company palette', name => {
    const theme = BUILTIN_THEMES[name]

    const colors = [...Object.values(theme.colors), ...Object.values(theme.terminal ?? {})]
      .filter((v): v is string => typeof v === 'string')
      .map(v => v.slice(0, 7).toLowerCase())

    for (const hex of colors) {
      expect(onLine(hex, [0x15, 0x78, 0x78]) || onLine(hex, [0, 255, 255]), hex).toBe(true)
    }
  })
})
