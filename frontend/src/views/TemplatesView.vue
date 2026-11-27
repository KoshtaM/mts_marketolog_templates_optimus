<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import MatchedMessagesDialog from '../components/MatchedMessagesDialog.vue'
import SegmentChart from '../components/SegmentChart.vue'
import TrendChart from '../components/TrendChart.vue'
import { batchName, batchPeriod, date, integer, money, moneyValue, period, share } from '../format'
import {
  analyze,
  benefitClass,
  isBusy,
  loadDashboard,
  loadTemplateTrend,
  reportError,
  selectBatch,
  state,
} from '../store'
import type { DaySegments, DriftFragment, TemplateMetrics, TemplateTrend } from '../types'

const selectedId = ref('')
const filter = ref('')
const templatedOnly = ref(false)
const sortKey = ref('monthly_net_benefit')
const sortDir = ref<-1 | 1>(-1)
const dialog = ref<{ id: string; heading: string; text: string } | null>(null)

const analysis = computed(() => state.analysis)

interface Header {
  key: string
  label: string
  narrow?: boolean
}

const headers: Header[] = [
  { key: 'text', label: 'Шаблон' },
  { key: 'operators', label: 'Операторы' },
  { key: 'matched_messages', label: 'Сообщений', narrow: true },
  { key: 'delivered_messages', label: 'Достав.', narrow: true },
  { key: 'triggered_messages', label: 'Срабат.', narrow: true },
  { key: 'trigger_rate', label: '% Срабат.', narrow: true },
  { key: 'monthly_actual_cost', label: 'Стоимость/мес' },
  { key: 'monthly_baseline_cost', label: 'Без шаблона/мес' },
  { key: 'template_fee', label: 'Шаблон/мес' },
  { key: 'monthly_net_benefit', label: 'Выгода/мес' },
  { key: 'share_of_all_segments', label: '% от всех' },
  { key: 'share_of_templated_segments', label: '% от шабл.' },
  { key: 'sender', label: 'Отправитель' },
]

const moneyKeys = new Set([
  'monthly_actual_cost',
  'monthly_baseline_cost',
  'template_fee',
  'monthly_net_benefit',
])

function sortValue(row: TemplateMetrics, key: string): string | number {
  if (key === 'operators') return row.operators.join(', ')
  if (moneyKeys.has(key)) return Number(row[key as keyof TemplateMetrics])
  const value = row[key as keyof TemplateMetrics]
  return typeof value === 'number' ? value : String(value ?? '')
}

const filtered = computed(() => {
  const query = filter.value.trim().toLowerCase()
  let rows = analysis.value?.metrics ?? []
  if (query) {
    rows = rows.filter((row) =>
      [row.text, row.sender, row.operators.join(' '), row.name].some((value) =>
        String(value).toLowerCase().includes(query),
      ),
    )
  }
  return [...rows].sort((left, right) => {
    const a = sortValue(left, sortKey.value)
    const b = sortValue(right, sortKey.value)
    if (typeof a === 'number' && typeof b === 'number') return (a - b) * sortDir.value
    return String(a).localeCompare(String(b), 'ru') * sortDir.value
  })
})

const selected = computed(
  () => analysis.value?.metrics.find((item) => item.template_id === selectedId.value) ?? null,
)

const totals = computed(() => {
  const metrics = analysis.value?.metrics ?? []
  let positive = 0
  let negative = 0
  for (const metric of metrics) {
    const value = Number(metric.monthly_net_benefit)
    if (value > 0) positive += value
    else negative += value
  }
  return { positive, negative, total: positive + negative }
})

const selectedTriggers = computed(() => {
  if (!selected.value || !analysis.value) return []
  return analysis.value.operator_triggers
    .filter((item) => item.template_id === selected.value?.template_id)
    .sort((a, b) => Number(b.listed) - Number(a.listed) || b.share - a.share)
})

const chartBase = computed<DaySegments[]>(() => {
  if (!analysis.value) return []
  if (templatedOnly.value) return analysis.value.daily_templated_segments
  if (state.dashboard?.batch?.id === analysis.value.batch_id) {
    return state.dashboard.daily_segments.map((item) => ({
      day: item.day,
      segments: item.segments,
    }))
  }
  return analysis.value.daily_total_segments
})

const chartCaption = computed(() => {
  if (!selected.value) return ''
  const matched = selected.value.matched_segments
  const base = chartBase.value.reduce((sum, item) => sum + item.segments, 0)
  return templatedOnly.value
    ? `шаблон: ${integer(matched)} из ${integer(base)} шаблонированных сегментов`
    : `шаблон: ${integer(matched)} из ${integer(base)} сегментов`
})

const summaryText = computed(() => {
  const view = analysis.value
  if (!view) return ''
  return (
    `${period(view.period_from, view.period_to)} · подпало ${integer(view.matched_message_count)} сообщений · ` +
    `срабатывание ${share(view.trigger_rate)} · выгода ${money(view.total_monthly_net_benefit, 0)}/мес · ` +
    `неактивных шаблонов ${integer(view.inactive_templates)}`
  )
})

function toggleSort(key: string): void {
  if (sortKey.value === key) sortDir.value = sortDir.value === 1 ? -1 : 1
  else {
    sortKey.value = key
    sortDir.value = -1
  }
}

function driftClass(kind: DriftFragment['kind']): string {
  if (kind === 'removed') return 'drift-removed'
  if (kind === 'added') return 'drift-added'
  return 'drift-equal'
}

function openMessages(metric: TemplateMetrics): void {
  dialog.value = {
    id: metric.template_id,
    heading: `Сообщения шаблона · ${metric.name || metric.template_id}`,
    text: metric.text,
  }
}

async function onBatch(event: Event): Promise<void> {
  await selectBatch((event.target as HTMLSelectElement).value)
}

async function runAnalysis(force = false): Promise<void> {
  await analyze(force)
}

watch(
  () => analysis.value,
  (view) => {
    if (!view) {
      selectedId.value = ''
      return
    }
    if (!view.metrics.some((item) => item.template_id === selectedId.value)) {
      selectedId.value = view.metrics[0]?.template_id ?? ''
    }
  },
  { immediate: true },
)

const trend = computed<TemplateTrend | null>(() => state.trend)
const deterioration = computed(() => state.trend?.deterioration ?? null)
const trendMetric = ref<'segments' | 'trigger_rate' | 'net_benefit'>('trigger_rate')

watch(
  () => selectedId.value,
  (templateId) => {
    if (templateId) void loadTemplateTrend(templateId)
  },
)

onMounted(() => {
  if (state.batchId) void analyze()
})
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy" :text="state.busyText" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Шаблоны</h1>
        <div class="page-subtitle">
          Подпадание, срабатывание и выгода зарегистрированных шаблонов
        </div>
      </div>
      <div class="toolbar">
        <select class="select" style="width: auto; max-width: 320px" :value="state.batchId" @change="onBatch">
          <option v-if="!state.batches.length" value="">Нет загрузок</option>
          <option v-for="batch in state.batches" :key="batch.id" :value="batch.id">
            {{ batchName(batch) }} · {{ batchPeriod(batch) }}
          </option>
        </select>
        <input v-model="filter" class="input" style="width: 220px" placeholder="Поиск по тексту, отправителю…" />
        <button class="btn" type="button" :disabled="isBusy || !state.batchId" @click="runAnalysis(true)">
          Пересчитать
        </button>
      </div>
    </header>

    <div v-if="!state.batchId" class="card empty">
      <h3>Нет загруженной статистики</h3>
      <p class="muted">Импортируйте выгрузку и список шаблонов, затем вернитесь на эту вкладку.</p>
      <RouterLink class="btn btn-primary" to="/import">Перейти к импорту</RouterLink>
    </div>

    <div v-else-if="!analysis" class="card empty">
      <h3>Анализ ещё не выполнен</h3>
      <p class="muted">Запустите расчёт, чтобы увидеть активность и экономику шаблонов.</p>
      <button class="btn btn-primary" type="button" @click="runAnalysis()">Выполнить анализ</button>
    </div>

    <template v-else>
      <section class="card table-card">
        <div class="table-wrap sticky-first" style="max-height: 440px">
          <table class="data">
            <thead>
              <tr>
                <th
                  v-for="header in headers"
                  :key="header.key"
                  :style="header.narrow ? 'width: 1%; white-space: nowrap' : ''"
                  data-sortable="true"
                  @click="toggleSort(header.key)"
                >
                  <span class="th-sort">
                    {{ header.label }}
                    <span v-if="sortKey === header.key" class="th-sort-indicator">{{ sortDir === 1 ? '▲' : '▼' }}</span>
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="metric in filtered"
                :key="metric.template_id"
                :class="[benefitClass(metric.monthly_net_benefit), { 'selected-row': metric.template_id === selectedId }]"
                @click="selectedId = metric.template_id"
              >
                <td style="min-width: 340px; max-width: 400px">
                  <button class="link-button cell-clamp" type="button" :title="metric.text" @click.stop="openMessages(metric)">
                    {{ metric.text }}
                  </button>
                </td>
                <td>
                  <span class="badge" :title="metric.operators.length ? metric.operators.join(', ') : 'все операторы'">
                    <span class="badge-text">{{ metric.operators.length ? metric.operators.join(', ') : 'все' }}</span>
                  </span>
                </td>
                <td class="num">{{ integer(metric.matched_messages) }}</td>
                <td class="num">{{ integer(metric.delivered_messages) }}</td>
                <td class="num">{{ integer(metric.triggered_messages) }}</td>
                <td class="num">{{ share(metric.trigger_rate) }}</td>
                <td class="num" :title="`Фактически за период: ${money(metric.actual_cost)}`">
                  {{ money(metric.monthly_actual_cost, 0) }}
                </td>
                <td class="num" :title="`Фактически за период: ${money(metric.baseline_cost)}`">
                  {{ money(metric.monthly_baseline_cost, 0) }}
                </td>
                <td class="num">{{ money(metric.template_fee, 0) }}</td>
                <td class="num">
                  <strong :class="Number(metric.monthly_net_benefit) >= 0 ? 'positive' : 'negative'">
                    {{ money(metric.monthly_net_benefit, 0) }}
                  </strong>
                </td>
                <td class="num">{{ share(metric.share_of_all_segments) }}</td>
                <td class="num">{{ share(metric.share_of_templated_segments) }}</td>
                <td class="cell-text" style="max-width: 160px" :title="metric.sender">{{ metric.sender || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!filtered.length" class="empty">Шаблоны не найдены. Импортируйте список шаблонов.</div>
        </div>
      </section>

      <div class="split-7-5">
        <section class="card chart-card">
          <div class="card-header">
            <div>
              <div class="card-title">Сегменты по дням</div>
              <div class="card-caption">
                {{ selected ? selected.name || selected.template_id : 'выберите шаблон в таблице' }}
              </div>
            </div>
            <label class="checkbox">
              <input v-model="templatedOnly" type="checkbox" />
              Только шаблонированные
            </label>
          </div>
          <div v-if="selected?.drift" class="drift-alert">
            <div class="drift-title">
              Текст сообщений изменился · похожесть {{ share(selected.drift.similarity) }}
            </div>
            <div class="drift-line">
              <span class="drift-label">Было</span>
              <span class="drift-text">
                <span
                  v-for="(fragment, index) in selected.drift.template_fragments"
                  :key="`before-${index}`"
                  :class="driftClass(fragment.kind)"
                >{{ fragment.text }}</span>
              </span>
            </div>
            <div class="drift-line">
              <span class="drift-label">Стало</span>
              <span class="drift-text">
                <span
                  v-for="(fragment, index) in selected.drift.candidate_fragments"
                  :key="`after-${index}`"
                  :class="driftClass(fragment.kind)"
                >{{ fragment.text }}</span>
              </span>
            </div>
          </div>
          <div v-if="selected" class="chart-fit">
            <SegmentChart
              :base="chartBase"
              :matched="selected.daily_segments"
              :caption="chartCaption"
              :matched-label="'Соответствуют шаблону'"
              :series-label="templatedOnly ? 'Остальной шаблонированный трафик' : 'Остальной трафик'"
              :height="240"
            />
          </div>
          <div v-else class="empty">Выберите шаблон, чтобы увидеть его сообщения по дням</div>
        </section>

        <section class="card operator-card">
          <div class="card-header">
            <div>
              <div class="card-title">Срабатывание по операторам</div>
              <div class="card-caption">
                {{ selected ? selected.name || selected.template_id : 'шаблон не выбран' }}
              </div>
            </div>
          </div>
          <div v-if="!selectedTriggers.length" class="empty">
            Нет разбивки: выберите шаблон или за период не было подпавших сообщений
          </div>
          <div v-else class="table-wrap fill">
            <table class="data">
              <thead>
                <tr>
                  <th>Оператор</th>
                  <th>В списке</th>
                  <th class="num">Подпало</th>
                  <th class="num">Сегментов</th>
                  <th class="num">Доля</th>
                  <th class="num">Срабатываний</th>
                  <th class="num">Срабатывание</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="trigger in selectedTriggers"
                  :key="`${trigger.template_id}-${trigger.operator}`"
                  :class="trigger.listed ? 'row-benefit-2' : 'row-loss'"
                >
                  <td>{{ trigger.operator }}</td>
                  <td>
                    <span :class="trigger.listed ? 'positive' : 'negative'">{{ trigger.listed ? '✓' : '✗' }}</span>
                  </td>
                  <td class="num">{{ integer(trigger.matched_messages) }}</td>
                  <td class="num">{{ integer(trigger.matched_segments) }}</td>
                  <td class="num">{{ share(trigger.share) }}</td>
                  <td class="num">{{ integer(trigger.triggered_messages) }}</td>
                  <td class="num">{{ share(trigger.trigger_rate) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section class="card trend-card">
        <div class="card-header">
          <div>
            <div class="card-title">История шаблона</div>
            <div class="card-caption">
              Тренд по загрузкам · {{ selected ? selected.name || selected.template_id : 'выберите шаблон в таблице' }}
            </div>
          </div>
          <div class="trend-metrics">
            <button class="btn" type="button" :class="{ active: trendMetric === 'trigger_rate' }" @click="trendMetric = 'trigger_rate'">
              Срабатывание
            </button>
            <button class="btn" type="button" :class="{ active: trendMetric === 'segments' }" @click="trendMetric = 'segments'">
              Сегменты
            </button>
            <button class="btn" type="button" :class="{ active: trendMetric === 'net_benefit' }" @click="trendMetric = 'net_benefit'">
              Выгода
            </button>
          </div>
        </div>
        <div v-if="selected && trend && trend.points.length" class="chart-fit">
          <TrendChart :points="trend.points" :metric="trendMetric" />
        </div>
        <p v-else class="card-caption">Нет сохранённых прогонов для тренда по загрузкам</p>
        <p v-if="deterioration" class="trend-alert">
          ▸ Алерт: шаблон «{{ selected?.text }}» перестал срабатывать — в предыдущей загрузке было
          {{ deterioration.previous_triggered_messages }} срабатываний, сейчас их {{ deterioration.current_triggered_messages }}.
          Возможно, изменился оператор, текст или отправитель.
        </p>
      </section>

      <section class="card benefit-strip">
        <div class="benefit-stats">
          <div class="benefit-stat">
            <span class="benefit-stat-label">Выгода выгодных шаблонов</span>
            <strong class="benefit-stat-value positive">{{ money(totals.positive, 0) }} <span>₽/мес</span></strong>
          </div>
          <div class="benefit-stat">
            <span class="benefit-stat-label">Убыток убыточных шаблонов</span>
            <strong class="benefit-stat-value negative">{{ money(totals.negative, 0) }} <span>₽/мес</span></strong>
          </div>
          <div class="benefit-stat">
            <span class="benefit-stat-label">Выгода всех шаблонов</span>
            <strong class="benefit-stat-value" :class="totals.total >= 0 ? 'positive' : 'negative'">
              {{ money(totals.total, 0) }} <span>₽/мес</span>
            </strong>
          </div>
        </div>
        <p class="card-caption benefit-note">{{ summaryText }}</p>
      </section>

      <details v-if="analysis.warnings.length" class="card warnings">
        <summary>▸ Предупреждения анализа · {{ analysis.warnings.length }}</summary>
        <ul>
          <li v-for="warning in analysis.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </details>
    </template>

    <MatchedMessagesDialog
      v-if="dialog && state.batchId"
      :batch-id="state.batchId"
      target-type="template"
      :target-id="dialog.id"
      :heading="dialog.heading"
      :text="dialog.text"
      @close="dialog = null"
    />
  </div>
</template>

<style scoped>
.table-card {
  padding: 0;
  overflow: hidden;
}

.table-card > .table-wrap {
  border: none;
  border-radius: calc(var(--radius-lg) - 1px);
}

.operator-card > .empty,
.chart-card > .empty {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.benefit-strip {
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 1.5);
}

.benefit-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: calc(var(--space) * 2);
}

.benefit-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: calc(var(--space) * 2);
  border-left: 3px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.benefit-stat:first-child {
  padding-left: 0;
  border-left: none;
}

.benefit-stat-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.benefit-stat-value {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.benefit-stat-value span {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0;
}

.benefit-note {
  margin: 0;
  padding-top: calc(var(--space) * 1.25);
  border-top: var(--border-width) solid var(--border);
}

.trend-card {
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 1.25);
}

.trend-metrics {
  display: flex;
  gap: calc(var(--space) * 1.5);
}

.trend-alert {
  margin: 0;
  padding: calc(var(--space) * 1.25) calc(var(--space) * 2);
  border: var(--border-width) solid color-mix(in srgb, var(--negative) 45%, transparent);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--negative) 8%, transparent);
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.drift-alert {
  margin: 0 0 calc(var(--space) * 1.25);
  padding: calc(var(--space) * 1.25) calc(var(--space) * 1.75);
  border: var(--border-width) solid color-mix(in srgb, var(--warning) 45%, transparent);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--warning) 8%, var(--surface));
}

.drift-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--warning);
}

.drift-line {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.45;
}

.drift-label {
  display: inline-block;
  min-width: 52px;
  color: var(--text-muted);
  font-weight: 600;
}

.drift-text > span {
  margin-right: 0.3em;
}

.drift-removed {
  color: var(--negative);
  text-decoration: line-through;
}

.drift-added {
  color: var(--positive);
  font-weight: 700;
}

@media (max-width: 1180px) {
  .benefit-stats {
    grid-template-columns: 1fr;
    gap: calc(var(--space) * 1.25);
  }

  .benefit-stat {
    padding-left: 0;
    border-left: none;
  }
}
</style>
