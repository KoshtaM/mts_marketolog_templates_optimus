<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import BatchDialog from '../components/BatchDialog.vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import { batchName, date, dateTime, integer, money, period } from '../format'
import {
  deleteAllBatches,
  deleteBatch,
  isBusy,
  loadDashboard,
  loadTemplates,
  renameBatch,
  reportError,
  setBatchPeriodLabel,
  state,
} from '../store'
import type { ImportReport, TemplateFilePreview, TemplateImportReport } from '../types'

const editor = ref<{ batchId: string; kind: 'name' | 'period_label'; initial: string | null } | null>(null)

async function openEditor(batchId: string, kind: 'name' | 'period_label'): Promise<void> {
  const batch = state.batches.find((item) => item.id === batchId)
  if (!batch) return
  editor.value = { batchId, kind, initial: kind === 'name' ? batch.name : batch.period_label }
}

async function onEditorSave(value: string | null): Promise<void> {
  if (!editor.value) return
  const { batchId, kind } = editor.value
  if (kind === 'name') {
    await renameBatch(batchId, value)
  } else {
    await setBatchPeriodLabel(batchId, value)
  }
  editor.value = null
}

function onEditorCancel(): void {
  editor.value = null
}

async function onDeleteBatch(batchId: string): Promise<void> {
  if (!window.confirm('Удалить загрузку? Сообщения и результаты анализа будут удалены безвозвратно.')) {
    return
  }
  await deleteBatch(batchId)
}

async function onDeleteAll(): Promise<void> {
  if (!state.batches.length) return
  if (!window.confirm(`Удалить все загрузки статистики (${state.batches.length})?`)) return
  await deleteAllBatches()
}

const statisticsInput = ref<HTMLInputElement | null>(null)
const templatesInput = ref<HTMLInputElement | null>(null)
const statisticsReport = ref<ImportReport | null>(null)
const templatesReport = ref<TemplateImportReport | null>(null)
const preview = ref<TemplateFilePreview | null>(null)
const mapping = ref<Record<string, string>>({})
const working = ref(false)
const step = ref('')

const mappingFields = [
  { key: 'text', label: 'Текст шаблона', required: true },
  { key: 'template_id', label: 'ID шаблона' },
  { key: 'name', label: 'Название' },
  { key: 'sender', label: 'Имя отправителя' },
  { key: 'active', label: 'Статус' },
  { key: 'monthly_fee', label: 'Стоимость' },
  { key: 'operators', label: 'Операторы' },
  { key: 'example', label: 'Текст (пример) шаблона' },
  { key: 'traffic_type', label: 'Тип трафика' },
]

const statisticsIssues = computed(() => statisticsReport.value?.issues.slice(0, 20) ?? [])

async function withLocalBusy<T>(text: string, operation: () => Promise<T>): Promise<T | null> {
  working.value = true
  step.value = text
  try {
    return await operation()
  } catch (error) {
    reportError(error)
    return null
  } finally {
    working.value = false
    step.value = ''
  }
}

async function importStatistics(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const report = await withLocalBusy('Импорт статистики…', () => api.importStatistics(file))
  input.value = ''
  if (!report) return
  statisticsReport.value = report
  const batches = await api.batches()
  state.batches = batches.batches
  await loadDashboard(report.batch.id)
}

async function previewTemplates(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await withLocalBusy('Чтение файла шаблонов…', () => api.previewTemplates(file))
  input.value = ''
  if (!result) return
  preview.value = result
  templatesReport.value = null
  const next: Record<string, string> = {}
  for (const field of mappingFields) {
    const suggested = result.suggested?.[field.key]
    if (suggested && result.columns.includes(suggested)) next[field.key] = suggested
  }
  mapping.value = next
}

async function importTemplates(): Promise<void> {
  if (!preview.value) return
  if (!mapping.value.text) {
    reportError(new Error('Выберите колонку с текстом шаблона'))
    return
  }
  const report = await withLocalBusy('Импорт шаблонов…', () =>
    api.importTemplates(preview.value!.upload_id, mapping.value),
  )
  if (!report) return
  templatesReport.value = report
  preview.value = null
  state.analysis = null
  state.analysisBatchId = ''
  await loadTemplates()
}

function resetPreview(): void {
  preview.value = null
  templatesReport.value = null
  mapping.value = {}
}
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy || working" :text="working ? step : state.busyText" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Импорт</h1>
        <div class="page-subtitle">
          Локальные Excel-выгрузки МТС-Маркетолога: статистика отправок и список шаблонов
        </div>
      </div>
      <div class="toolbar">
        <RouterLink class="btn" to="/">На дашборд</RouterLink>
      </div>
    </header>

    <div class="import-grid">
      <section class="card import-card">
        <div class="card-header">
          <div>
            <div class="card-title">Статистика отправок</div>
            <div class="card-caption">Стандартная выгрузка из личного кабинета, лист Excel</div>
          </div>
          <span class="badge">.xlsx</span>
        </div>
        <p class="small muted">
          Повторный импорт того же файла идемпотентен: загрузка определяется по SHA-256.
          Дубликаты ID сообщения суммируются, сообщение считается один раз.
        </p>
        <input ref="statisticsInput" type="file" accept=".xlsx,.xlsm" hidden @change="importStatistics" />
        <button class="btn btn-primary" type="button" :disabled="working" @click="statisticsInput?.click()">
          Выбрать файл статистики
        </button>

        <div v-if="statisticsReport" class="report">
          <div class="report-title">
            Импорт завершён
            <span v-if="statisticsReport.reused" class="badge">файл уже загружался</span>
          </div>
          <div class="details-grid">
            <span>Файл</span><strong>{{ statisticsReport.batch.source_name }}</strong>
            <span>Период</span><strong>{{ period(statisticsReport.batch.period_from, statisticsReport.batch.period_to) }}</strong>
            <span>Строк</span><strong>{{ integer(statisticsReport.batch.row_count) }}</strong>
            <span>Сообщений</span><strong>{{ integer(statisticsReport.batch.message_count) }}</strong>
            <span>Сегментов</span><strong>{{ integer(statisticsReport.segment_count) }}</strong>
            <span>Стоимость</span><strong>{{ money(statisticsReport.batch.total_cost) }}</strong>
            <span>Доставлено</span><strong>{{ integer(statisticsReport.delivered_rows) }}</strong>
            <span>Частично доставлено</span><strong>{{ integer(statisticsReport.partial_delivered_rows) }}</strong>
            <span>Ошибки отправки</span><strong>{{ integer(statisticsReport.send_error_rows) }}</strong>
            <span>Ошибки доставки</span><strong>{{ integer(statisticsReport.delivery_error_rows) }}</strong>
            <span>Пустой пакет</span><strong>{{ integer(statisticsReport.empty_package_rows) }}</strong>
            <span>Дубликаты ID</span><strong>{{ integer(statisticsReport.duplicate_message_ids) }}</strong>
          </div>
          <div v-if="statisticsReport.batch.warnings.length" class="report-block">
            <div class="report-title">Предупреждения</div>
            <ul class="small">
              <li v-for="warning in statisticsReport.batch.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>
          <div v-if="statisticsIssues.length" class="report-block">
            <div class="report-title">Расхождения в данных · {{ statisticsReport.issues.length }}</div>
            <div class="table-wrap" style="max-height: 180px">
              <table class="data">
                <thead>
                  <tr><th>ID сообщения</th><th>Поле</th><th>Детали</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(issue, index) in statisticsIssues" :key="`${issue.message_id}-${index}`">
                    <td class="mono">{{ issue.message_id }}</td>
                    <td>{{ issue.field }}</td>
                    <td>{{ issue.detail }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section class="card import-card">
        <div class="card-header">
          <div>
            <div class="card-title">Список шаблонов</div>
            <div class="card-caption">Выгрузка шаблонов: колонки сопоставляются вручную</div>
          </div>
          <span class="badge">.xlsx</span>
        </div>
        <p class="small muted">
          Один шаблон на нескольких операторов объединяется по отправителю и точному тексту.
          Плата за шаблон взимается один раз.
        </p>
        <input ref="templatesInput" type="file" accept=".xlsx,.xlsm" hidden @change="previewTemplates" />
        <button class="btn btn-primary" type="button" :disabled="working" @click="templatesInput?.click()">
          Выбрать файл шаблонов
        </button>

        <div v-if="preview" class="report">
          <div class="report-title">Сопоставление колонок · {{ preview.source_name }}</div>
          <div class="mapping-grid">
            <label v-for="field in mappingFields" :key="field.key" class="field">
              <span class="field-label">{{ field.label }}<span v-if="field.required"> *</span></span>
              <select v-model="mapping[field.key]" class="select">
                <option value="">— не использовать —</option>
                <option v-for="column in preview.columns" :key="column" :value="column">{{ column }}</option>
              </select>
            </label>
          </div>

          <div class="report-block">
            <div class="report-title">Первые строки файла</div>
            <div class="table-wrap" style="max-height: 190px">
              <table class="data">
                <thead>
                  <tr>
                    <th v-for="column in preview.columns" :key="column">{{ column }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in preview.sample_rows.slice(0, 5)" :key="index">
                    <td v-for="column in preview.columns" :key="column" class="cell-text" style="max-width: 180px">
                      {{ row[column] ?? '' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="row">
            <button class="btn btn-primary" type="button" :disabled="working || !mapping.text" @click="importTemplates">
              Импортировать шаблоны
            </button>
            <button class="btn" type="button" :disabled="working" @click="resetPreview">Отмена</button>
          </div>
        </div>

        <div v-if="templatesReport" class="report">
          <div class="report-title">Шаблоны импортированы</div>
          <div class="details-grid">
            <span>Добавлено</span><strong>{{ integer(templatesReport.imported) }}</strong>
            <span>Обновлено</span><strong>{{ integer(templatesReport.updated) }}</strong>
            <span>Дубликатов</span><strong>{{ integer(templatesReport.duplicates) }}</strong>
            <span>Пропущено пустых</span><strong>{{ integer(templatesReport.skipped_empty) }}</strong>
            <span>Удалено</span><strong>{{ integer(templatesReport.removed) }}</strong>
          </div>
          <ul v-if="templatesReport.warnings.length" class="small" style="margin-top: 10px">
            <li v-for="warning in templatesReport.warnings" :key="warning">{{ warning }}</li>
          </ul>
        </div>
      </section>
    </div>

    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Загруженные статистики</div>
          <div class="card-caption">Все импортированные файлы в локальной базе</div>
        </div>
        <button class="btn" type="button" :disabled="working" @click="loadDashboard(state.batchId)">Обновить</button>
        <button class="btn" type="button" :disabled="working || !state.batches.length" @click="onDeleteAll">
          Удалить все
        </button>
      </div>
      <p v-if="state.batches.length" class="field-hint" style="margin: 10px 0">
        Удаление загрузки удаляет сообщения, биллинговые строки и результаты анализа безвозвратно.
        Шаблоны и настройки при этом не трогаются. Исходный файл на диске не удаляется.
      </p>
      <div v-if="!state.batches.length" class="empty">Загрузок пока нет</div>
      <div v-else class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>Загрузка</th>
              <th class="num">Сообщений</th>
              <th class="num">Сегментов</th>
              <th class="num">Стоимость</th>
              <th>Импортирован</th>
              <th>Период</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="batch in state.batches"
              :key="batch.id"
              :class="{ 'selected-row': batch.id === state.batchId }"
              style="cursor: pointer"
              @click="loadDashboard(batch.id)"
            >
              <td>
                <div class="cell-text" :title="batch.source_name">{{ batchName(batch) }}</div>
              </td>
              <td class="num">{{ integer(batch.message_count) }}</td>
              <td class="num">{{ integer(batch.segment_count) }}</td>
              <td class="num">{{ money(batch.total_cost, 0) }}</td>
              <td>{{ dateTime(batch.imported_at) }}</td>
              <td>{{ period(batch.period_from, batch.period_to) }}</td>
              <td><span class="badge">{{ batch.status }}</span></td>
              <td class="num" @click.stop>
                <button
                  class="btn btn-ghost"
                  type="button"
                  title="Переименовать"
                  @click="openEditor(batch.id, 'name')"
                >
                  ✎
                </button>
                <button
                  class="btn btn-ghost"
                  type="button"
                  title="Метка периода"
                  @click="openEditor(batch.id, 'period_label')"
                >
                  ≡
                </button>
                <button
                  class="btn btn-ghost"
                  type="button"
                  title="Удалить"
                  @click="onDeleteBatch(batch.id)"
                >
                  🗑
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <BatchDialog
        v-if="editor"
        :key="editor.batchId"
        :title="editor.kind === 'name' ? 'Переименовать загрузку' : 'Метка периода'"
        :label="editor.kind === 'name' ? 'Название загрузки' : 'Метка периода'"
        :placeholder="editor.kind === 'name' ? 'Например, «Октябрь — полная выгрузка»' : 'Например, «Октябрь 2026»'"
        :initial="editor.initial"
        @save="onEditorSave"
        @cancel="onEditorCancel"
      />
    </section>
  </div>
</template>

<style scoped>
.import-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: calc(var(--space) * 2);
  align-items: stretch;
}

.import-card {
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 1.5);
}

.report {
  border-top: var(--border-width) dashed var(--border);
  padding-top: calc(var(--space) * 1.5);
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 1.25);
}

.report-title {
  font-weight: 700;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.report-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.details-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 5px 14px;
  font-size: 12px;
}

.details-grid span {
  color: var(--text-muted);
}

.mapping-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: calc(var(--space) * 1.25);
}

@media (max-width: 1180px) {
  .import-grid {
    grid-template-columns: 1fr;
  }
}
</style>
