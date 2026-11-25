import { reactive } from 'vue'
import type { Theme, ThemePalette } from './types'

export const SYSTEM_PALETTE: ThemePalette = {
  window: '#f4f6fa',
  surface: '#ffffff',
  surface_alt: '#eef2f7',
  text: '#1f2a37',
  text_muted: '#667085',
  accent: '#1f6feb',
  accent_hover: '#1a5fd0',
  accent_text: '#ffffff',
  border: '#d7dee8',
  header: '#dce9f8',
  header_text: '#475467',
  selection: '#dbeafe',
  selection_text: '#1f2a37',
  positive: '#1b7f3a',
  negative: '#b42318',
  accent_secondary: '#8b1a3a',
  accent_pressed: '#1650b0',
  focus_ring: '#1f6feb',
  warning: '#b54708',
  shadow: '#98a2b3',
}

export const activePalette = reactive<ThemePalette>({ ...SYSTEM_PALETTE })

const CSS_VARIABLES: Record<keyof ThemePalette, string> = {
  window: '--window',
  surface: '--surface',
  surface_alt: '--surface-alt',
  text: '--text',
  text_muted: '--text-muted',
  accent: '--accent',
  accent_hover: '--accent-hover',
  accent_text: '--accent-text',
  border: '--border',
  header: '--header',
  header_text: '--header-text',
  selection: '--selection',
  selection_text: '--selection-text',
  positive: '--positive',
  negative: '--negative',
  accent_secondary: '--accent-secondary',
  accent_pressed: '--accent-pressed',
  focus_ring: '--focus-ring',
  warning: '--warning',
  shadow: '--shadow',
}

export function applyTheme(theme: Theme | undefined): void {
  const root = document.documentElement
  const palette = theme?.palette ?? SYSTEM_PALETTE
  Object.assign(activePalette, palette)
  const entries = Object.entries(CSS_VARIABLES) as [keyof ThemePalette, string][]
  for (const [key, variable] of entries) {
    root.style.setProperty(variable, palette[key])
  }
  const fontFamily = theme?.font_family?.trim() || 'Segoe UI'
  const headingFont = theme?.font_heading?.trim() || fontFamily
  const monoFont = theme?.font_mono?.trim() || 'Cascadia Mono, Consolas, monospace'
  root.style.setProperty('--font-family', `"${fontFamily}", "Segoe UI", system-ui, sans-serif`)
  root.style.setProperty('--font-heading', `"${headingFont}", "Segoe UI", system-ui, sans-serif`)
  root.style.setProperty('--font-mono', `"${monoFont}", Consolas, monospace`)
  root.style.setProperty('--font-size', `${(theme?.font_size ?? 10) + 4}px`)
  root.style.setProperty('--radius', `${theme?.radius ?? 8}px`)
  root.style.setProperty('--border-width', `${theme?.border_width ?? 1}px`)
  const spacing = theme?.spacing_scale ?? 1
  root.style.setProperty('--space', `${Math.round(8 * spacing)}px`)
  root.dataset.theme = theme?.id ?? 'system'
  root.dataset.hardShadow = theme?.hard_shadow ? 'true' : 'false'
  root.dataset.bold = theme?.bold_text ? 'true' : 'false'
}

const OPERATOR_COLORS: Record<string, string> = {
  мтс: '#e30611',
  mts: '#e30611',
  tele2: '#1d1d1f',
  мегафон: '#00b956',
  megafon: '#00b956',
  билайн: '#ffcc00',
  beeline: '#ffcc00',
  ростелеком: '#7b4dff',
  rostelecom: '#7b4dff',
  other_rf: '#98a2b3',
  sbertelecom: '#21a038',
  smarts_motiv: '#ff7a00',
  international: '#00a3c4',
  другие: '#98a2b3',
}

export function operatorColor(name: string): string {
  const normalized = name.trim().toLowerCase()
  return OPERATOR_COLORS[normalized] ?? '#8b6cef'
}

export const TEMPLATED_COLOR = '#0d9488'
export const MATCHED_COLOR = '#ff8c00'
export const ORDINARY_COLOR = '#b42318'
