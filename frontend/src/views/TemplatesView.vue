<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import MatchedMessagesDialog from '../components/MatchedMessagesDialog.vue'
import SegmentChart from '../components/SegmentChart.vue'
import { date, integer, money, moneyValue, period, share } from '../format'
import {
  analyze,
  benefitClass,
  isBusy,
  selectBatch,
  state,
} from '../store'
import type { DaySegments, TemplateMetrics } from '../types'

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
            {{ batch.source_name }} · {{ date(batch.period_from) }}
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
      <section class="card">
        <div class="table-wrap" style="max-height: 430px">
          <table class="data">
            <thead>
              <tr>
                <th
                  v-for="header in headers"
                  :key="header.key"
                  :style="header.narrow ? 'width: 1%; white-space: nowrap' : ''"
                  @click="toggleSort(header.key)"
                >
                  <span class="th-sort">
                    {{ header.label }}
                    <span v-if="sortKey === header.key">{{ sortDir === 1 ? '▲' : '▼' }}</span>
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
                <td style="min-width: 280px">
                  <button class="link-button" type="button" :title="metric.text" @click.stop="openMessages(metric)">
                    {{ metric.text }}
                  </button>
                </td>
                <td>
                  <span class="badge" :title="metric.operators.length ? metric.operators.join(', ') : 'все операторы'">
                    {{ metric.operators.length ? metric.operators.join(', ') : 'все' }}
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

      <div class="lower-grid">
        <section class="card">
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
          <SegmentChart
            v-if="selected"
            :base="chartBase"
            :matched="selected.daily_segments"
            :caption="chartCaption"
            :matched-label="'Соответствуют шаблону'"
            :series-label="templatedOnly ? 'Остальной шаблонированный трафик' : 'Остальной трафик'"
            :height="200"
          />
          <div v-else class="empty">Выберите шаблон, чтобы увидеть его сообщения по дням</div>
        </section>

        <div class="stack">
          <section class="card">
            <div class="card-header">
              <div class="card-title">Выгода шаблонов</div>
              <div class="card-caption">в месяц, все шаблоны</div>
            </div>
            <div class="benefit-lines">
              <div class="benefit-line">
                <strong class="positive">{{ money(totals.positive, 0) }}</strong>
                <span>Выгода выгодных шаблонов, ₽/мес</span>
              </div>
              <div class="benefit-line">
                <strong class="negative">{{ money(totals.negative, 0) }}</strong>
                <span>Убыток убыточных шаблонов, ₽/мес</span>
              </div>
              <div class="benefit-line">
                <strong :class="totals.total >= 0 ? 'positive' : 'negative'">{{ money(totals.total, 0) }}</strong>
                <span>Выгода всех шаблонов, ₽/мес</span>
              </div>
            </div>
            <p class="card-caption" style="margin-top: 10px">{{ summaryText }}</p>
          </section>

          <section class="card">
            <div class="card-header">
              <div>
                <div class="card-title">Срабатывание по операторам получателя</div>
                <div class="card-caption">
                  {{ selected ? selected.name || selected.template_id : 'шаблон не выбран' }}
                </div>
              </div>
            </div>
            <div v-if="!selectedTriggers.length" class="empty" style="padding: 20px">
              Нет разбивки: выберите шаблон или за период не было подпавших сообщений
            </div>
            <div v-else class="table-wrap" style="max-height: 210px">
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
                    <td>{{ trigger.listed ? '✓' : '✗' }}</td>
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

          <details v-if="analysis.warnings.length" class="card warnings">
            <summary>▸ Предупреждения анализа · {{ analysis.warnings.length }}</summary>
            <ul>
              <li v-for="warning in analysis.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </details>
        </div>
      </div>
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
.th-sort {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
}

.lower-grid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: calc(var(--space) * 2);
  align-items: start;
}

.benefit-lines {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.benefit-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.benefit-line strong {
  font-size: 19px;
  min-width: 120px;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 1180px) {
  .lower-grid {
    grid-template-columns: 1fr;
  }
}
</style>
