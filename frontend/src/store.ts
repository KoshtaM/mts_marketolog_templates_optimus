import { computed, reactive } from 'vue'
import { ApiError, api } from './api'
import { applyTheme } from './theme'
import type {
  ActionCenter,
  Analysis,
  AppSettings,
  DashboardSummary,
  ImportBatch,
  ImportReport,
  MatchedMessage,
  SmsTemplate,
  TemplateTrend,
  Theme,
} from './types'

const BATCH_KEY = 'mts-templates-batch'
const MIN_BUSY_MS = 450

interface State {
  ready: boolean
  error: string
  busyCount: number
  busyText: string
  settings: AppSettings | null
  themes: Theme[]
  batches: ImportBatch[]
  batchId: string
  dashboard: DashboardSummary | null
  analysis: Analysis | null
  analysisBatchId: string
  actionCenter: ActionCenter | null
  actionCenterBatchId: string
  templates: SmsTemplate[]
  trend: TemplateTrend | null
  trendTemplateId: string
}

export const state = reactive<State>({
  ready: false,
  error: '',
  busyCount: 0,
  busyText: '',
  settings: null,
  themes: [],
  batches: [],
  batchId: '',
  dashboard: null,
  analysis: null,
  analysisBatchId: '',
  actionCenter: null,
  actionCenterBatchId: '',
  templates: [],
  trend: null,
  trendTemplateId: '',
})

export const isBusy = computed(() => state.busyCount > 0)

export const currentBatch = computed(
  () => state.batches.find((item) => item.id === state.batchId) ?? null,
)

export const currentTheme = computed(
  () => state.themes.find((item) => item.id === state.settings?.theme) ?? state.themes[0],
)

export const benefitThresholds = computed<number[]>(() => {
  const raw = state.settings?.benefit_thresholds ?? []
  const levels = raw.map((item) => Number(item)).filter((item) => Number.isFinite(item))
  return levels.length === 5 ? levels : [1, 3000, 10000, 30000, 100000]
})

export function benefitLevel(value: string | number): number {
  const amount = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(amount) || amount <= 0) return 0
  const levels = benefitThresholds.value
  let level = 0
  for (let index = 0; index < levels.length; index += 1) {
    if (amount >= levels[index]) level = index + 1
  }
  return level
}

export function benefitClass(value: string | number): string {
  const amount = typeof value === 'number' ? value : Number(value)
  if (amount < 0) return 'row-loss'
  const level = benefitLevel(amount)
  return level > 0 ? `row-benefit-${level}` : ''
}

export function reportError(error: unknown): void {
  if (error instanceof ApiError) {
    state.error = error.message
  } else if (error instanceof Error) {
    state.error = error.message
  } else {
    state.error = 'Неизвестная ошибка'
  }
}

export function clearError(): void {
  state.error = ''
}

async function withBusy<T>(text: string, operation: () => Promise<T>): Promise<T> {
  state.busyCount += 1
  state.busyText = text
  const started = Date.now()
  try {
    return await operation()
  } finally {
    const remaining = MIN_BUSY_MS - (Date.now() - started)
    if (remaining > 0) {
      await new Promise((resolve) => setTimeout(resolve, remaining))
    }
    state.busyCount = Math.max(0, state.busyCount - 1)
    if (state.busyCount === 0) state.busyText = ''
  }
}

export async function init(): Promise<void> {
  try {
    const [settings, themes, batches] = await Promise.all([
      api.settings(),
      api.themes(),
      api.batches(),
    ])
    state.settings = settings
    state.themes = themes.themes
    state.batches = batches.batches
    applyTheme(currentTheme.value)
    const stored = localStorage.getItem(BATCH_KEY)
    const preferred = batches.batches.find((item) => item.id === stored) ?? batches.batches[0]
    state.batchId = preferred?.id ?? ''
    await loadDashboard(state.batchId)
    await loadTemplates()
    state.ready = true
  } catch (error) {
    reportError(error)
    state.ready = true
  }
}

export async function loadDashboard(batchId = state.batchId): Promise<void> {
  state.batchId = batchId
  if (batchId) localStorage.setItem(BATCH_KEY, batchId)
  try {
    state.dashboard = await api.dashboard(batchId || undefined)
    if (state.analysis && state.analysisBatchId !== batchId) {
      state.analysis = null
      state.analysisBatchId = ''
    }
    if (state.actionCenter && state.actionCenterBatchId !== batchId) {
      state.actionCenter = null
      state.actionCenterBatchId = ''
    }
  } catch (error) {
    reportError(error)
  }
}

export async function refreshAll(): Promise<void> {
  await withBusy('Обновление данных…', async () => {
    const [batches, dashboard] = await Promise.all([
      api.batches(),
      api.dashboard(state.batchId || undefined),
    ])
    state.batches = batches.batches
    state.dashboard = dashboard
    state.analysis = null
    state.analysisBatchId = ''
    state.actionCenter = null
    state.actionCenterBatchId = ''
    if (state.batchId && !state.batches.some((item) => item.id === state.batchId)) {
      state.batchId = state.batches[0]?.id ?? ''
    }
    await loadTemplates()
  })
}

export async function selectBatch(batchId: string): Promise<void> {
  if (batchId === state.batchId) return
  state.analysis = null
  state.analysisBatchId = ''
  state.actionCenter = null
  state.actionCenterBatchId = ''
  await loadDashboard(batchId)
}

export async function loadTemplateTrend(templateId: string): Promise<void> {
  if (!state.batchId) return
  try {
    state.trendTemplateId = templateId
    state.trend = await api.templateTrend(templateId)
  } catch (error) {
    reportError(error)
  }
}

export async function renameBatch(batchId: string, name: string | null): Promise<void> {
  try {
    const updated = await withBusy('Переименование загрузки…', () => api.renameBatch(batchId, name))
    state.batches = state.batches.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
    if (state.batchId === updated.id) {
      state.dashboard = state.dashboard ? { ...state.dashboard, batch: updated } : state.dashboard
    }
  } catch (error) {
    reportError(error)
  }
}

export async function setBatchPeriodLabel(batchId: string, periodLabel: string | null): Promise<void> {
  try {
    const updated = await withBusy(
      'Метка периода…',
      () => api.setBatchPeriodLabel(batchId, periodLabel),
    )
    state.batches = state.batches.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
    if (state.batchId === updated.id) {
      state.dashboard = state.dashboard ? { ...state.dashboard, batch: updated } : state.dashboard
    }
  } catch (error) {
    reportError(error)
  }
}

export async function deleteBatch(batchId: string): Promise<void> {
  try {
    await withBusy('Удаление загрузки…', () => api.deleteBatch(batchId))
    const batches = (await api.batches()).batches
    state.batches = batches
    state.analysis = null
    state.analysisBatchId = ''
    state.actionCenter = null
    state.actionCenterBatchId = ''
    if (state.batchId === batchId) {
      state.batchId = batches[0]?.id ?? ''
    }
    await loadDashboard(state.batchId)
    await loadTemplates()
  } catch (error) {
    reportError(error)
  }
}

export async function deleteAllBatches(): Promise<void> {
  try {
    await withBusy('Удаление загрузок…', () => api.deleteAllBatches())
    state.batches = []
    state.batchId = ''
    state.dashboard = null
    state.analysis = null
    state.analysisBatchId = ''
    state.actionCenter = null
    state.actionCenterBatchId = ''
    localStorage.removeItem(BATCH_KEY)
    await loadTemplates()
  } catch (error) {
    reportError(error)
  }
}

export async function loadTemplates(): Promise<void> {
  try {
    const response = await api.templates()
    state.templates = response.templates
  } catch (error) {
    reportError(error)
  }
}

export async function analyze(force = false): Promise<Analysis | null> {
  if (!state.batchId) return null
  if (!force && state.analysis && state.analysisBatchId === state.batchId) {
    return state.analysis
  }
  try {
    const analysis = await withBusy(
      force ? 'Пересчёт анализа…' : 'Выполняется анализ…',
      () => api.analysis(state.batchId, true, force),
    )
    state.analysis = analysis
    state.analysisBatchId = state.batchId
    return analysis
  } catch (error) {
    reportError(error)
    return null
  }
}

export async function loadActionCenter(force = false): Promise<ActionCenter | null> {
  if (!state.batchId) return null
  if (!force && state.actionCenter && state.actionCenterBatchId === state.batchId) {
    return state.actionCenter
  }
  try {
    const center = await withBusy(
      force ? 'Пересчёт центра действий…' : 'Собираем центр действий…',
      () => api.actionCenter(state.batchId, force),
    )
    state.actionCenter = center
    state.actionCenterBatchId = state.batchId
    return center
  } catch (error) {
    reportError(error)
    return null
  }
}

export async function saveSettings(changes: Partial<AppSettings>): Promise<AppSettings | null> {
  try {
    const settings = await withBusy('Сохранение настроек…', () => api.updateSettings(changes))
    state.settings = settings
    applyTheme(currentTheme.value)
    state.analysis = null
    state.analysisBatchId = ''
    state.actionCenter = null
    state.actionCenterBatchId = ''
    return settings
  } catch (error) {
    reportError(error)
    return null
  }
}

export async function setTheme(themeId: string): Promise<void> {
  const previous = state.settings?.theme
  if (state.settings) state.settings.theme = themeId
  applyTheme(currentTheme.value)
  const saved = await saveSettings({ theme: themeId })
  if (!saved && state.settings) {
    state.settings.theme = previous ?? 'system'
    applyTheme(currentTheme.value)
  }
}

export function resetToSystemTheme(): void {
  void setTheme('system')
}
