import type {
  ActionCenter,
  Analysis,
  AppSettings,
  DashboardSummary,
  ImportBatch,
  ImportReport,
  MatchedMessage,
  SmsTemplate,
  TemplateFilePreview,
  TemplateImportReport,
  Theme,
} from './types'

const PREFIX = '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${PREFIX}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`
    try {
      const payload = await response.json()
      if (payload && typeof payload.detail === 'string') {
        message = payload.detail
      }
    } catch {
      // тело ответа не JSON — оставляем общий текст
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${PREFIX}${path}`, { method: 'POST', body: form })
  if (!response.ok) {
    let message = `Ошибка загрузки (${response.status})`
    try {
      const payload = await response.json()
      if (payload && typeof payload.detail === 'string') {
        message = payload.detail
      }
    } catch {
      // тело ответа не JSON
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  themes: () => request<{ themes: Theme[] }>('/themes'),

  settings: () => request<AppSettings>('/settings'),

  updateSettings: (changes: Partial<AppSettings>) =>
    request<AppSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(changes),
    }),

  batches: () => request<{ batches: ImportBatch[] }>('/batches'),

  dashboard: (batchId?: string) =>
    request<DashboardSummary>(
      `/dashboard${batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ''}`,
    ),

  analysis: (batchId: string, includeCandidates = true, force = false) =>
    request<Analysis>('/analysis', {
      method: 'POST',
      body: JSON.stringify({
        batch_id: batchId,
        include_candidates: includeCandidates,
        force,
      }),
    }),

  templates: () => request<{ templates: SmsTemplate[] }>('/templates'),

  importStatistics: (file: File) =>
    upload<ImportReport>('/imports/statistics', file),

  previewTemplates: (file: File) =>
    upload<TemplateFilePreview>('/imports/templates/preview', file),

  importTemplates: (uploadId: string, mapping?: Record<string, string>) => {
    const form = new FormData()
    form.append('upload_id', uploadId)
    if (mapping) {
      form.append('mapping_json', JSON.stringify(mapping))
    }
    return fetch(`${PREFIX}/imports/templates`, { method: 'POST', body: form }).then(
      async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => null)
          throw new ApiError(
            payload?.detail ?? `Ошибка импорта шаблонов (${response.status})`,
            response.status,
          )
        }
        return (await response.json()) as TemplateImportReport
      },
    )
  },

  matchedTemplateMessages: (
    batchId: string,
    templateId: string,
    options: { operator?: string | null; untriggered?: boolean } = {},
  ) => {
    const params = new URLSearchParams({ batch_id: batchId })
    if (options.operator) params.set('operator', options.operator)
    if (options.untriggered) params.set('untriggered', 'true')
    return request<{ messages: MatchedMessage[] }>(
      `/matched-messages/template/${encodeURIComponent(templateId)}?${params.toString()}`,
    )
  },

  unmatchedTemplatedMessages: (batchId: string) =>
    request<{ messages: MatchedMessage[] }>(
      `/matched-messages/unmatched-templated?batch_id=${encodeURIComponent(batchId)}`,
    ),

  actionCenter: (batchId: string, force = false) =>
    request<ActionCenter>(
      `/action-center?batch_id=${encodeURIComponent(batchId)}${force ? '&force=true' : ''}`,
    ),

  matchedCandidateMessages: (batchId: string, candidateId: string) =>
    request<{ messages: MatchedMessage[] }>(
      `/matched-messages/candidate/${encodeURIComponent(candidateId)}?batch_id=${encodeURIComponent(batchId)}`,
    ),

  exportReport: async (batchId: string): Promise<Blob> => {
    const response = await fetch(`${PREFIX}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId }),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new ApiError(
        payload?.detail ?? `Ошибка экспорта (${response.status})`,
        response.status,
      )
    }
    return await response.blob()
  },
}
