<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import DistributionChart from '../components/DistributionChart.vue'
import DonutChart from '../components/DonutChart.vue'
import KpiCard from '../components/KpiCard.vue'
import ShareMeter from '../components/ShareMeter.vue'
import StackedBarChart from '../components/StackedBarChart.vue'
import StructureBars from '../components/StructureBars.vue'
import { groupBuckets } from '../distribution'
import { batchName, batchPeriod, date, integer, money, moneyValue, period, share } from '../format'
import { isBusy, loadDashboard, refreshAll, selectBatch, state } from '../store'
import { ORDINARY_COLOR, TEMPLATED_COLOR, operatorColor } from '../theme'

const mode = ref<'overview' | 'subscribers'>('overview')

const summary = computed(() => state.dashboard)
const statistics = computed(() => summary.value?.statistics ?? null)
const segmentation = computed(() => summary.value?.segmentation ?? null)

const classesRows = computed(() => {
  if (!statistics.value) return []
  const stats = statistics.value
  return [
    {
      name: 'Всего',
      messages: stats.message_count,
      segments: stats.segments,
      cost: stats.cost,
      average: stats.average_segment_cost,
      shareValue: 1,
      tone: 'var(--text)',
    },
    {
      name: 'Обычные',
      messages: stats.ordinary_messages,
      segments: stats.ordinary_segments,
      cost: stats.ordinary_cost,
      average: stats.ordinary_average_segment_cost,
      shareValue: stats.ordinary_segment_share,
      tone: ORDINARY_COLOR,
    },
    {
      name: 'Шаблонированные',
      messages: stats.templated_messages,
      segments: stats.templated_segments,
      cost: stats.templated_cost,
      average: stats.templated_average_segment_cost,
      shareValue: stats.templated_segment_share,
      tone: TEMPLATED_COLOR,
    },
  ]
})

const dailyItems = computed(() =>
  (summary.value?.daily_segments ?? []).map((item) => {
    const parts = [...item.operators]
      .filter((operator) => operator.segments > 0)
      .sort((a, b) => b.segments - a.segments)
      .map((operator) => ({
        name: operator.operator,
        value: operator.segments,
        color: operatorColor(operator.operator),
      }))
    return { label: item.day.slice(8, 10) + '.' + item.day.slice(5, 7), total: item.segments, parts }
  }),
)

const topOperators = computed(() => {
  const operators = [...(summary.value?.operators ?? [])].sort((a, b) => b.messages - a.messages)
  const head = operators.slice(0, 6)
  const tail = operators.slice(6)
  const rows = head.map((item) => ({
    name: item.operator,
    messages: item.messages,
    segments: item.segments,
    cost: item.cost,
    shareValue: item.messages / Math.max(1, statistics.value?.message_count ?? 1),
    color: operatorColor(item.operator),
  }))
  if (tail.length) {
    rows.push({
      name: 'Другие',
      messages: tail.reduce((sum, item) => sum + item.messages, 0),
      segments: tail.reduce((sum, item) => sum + item.segments, 0),
      cost: String(tail.reduce((sum, item) => sum + moneyValue(item.cost), 0)),
      shareValue: tail.reduce((sum, item) => sum + item.messages, 0) / Math.max(1, statistics.value?.message_count ?? 1),
      color: operatorColor('Другие'),
    })
  }
  return rows
})

const concentration = computed(() => {
  const rows = [...topOperators.value].filter((row) => row.name !== 'Другие')
  if (!rows.length) return ''
  const largest = rows[0]
  const top3 = rows.slice(0, 3).reduce((sum, row) => sum + row.shareValue, 0)
  return `Крупнейший — ${largest.name}: ${share(largest.shareValue, 0)} сообщений · топ-3 — ${share(top3, 0)}`
})

const costShares = computed(() => {
  const total = moneyValue(statistics.value?.cost ?? '0')
  const templated = moneyValue(statistics.value?.templated_cost ?? '0')
  const templatedShare = total > 0 ? templated / total : 0
  return { templated: templatedShare, ordinary: Math.max(0, 1 - templatedShare) }
})

const cheaperHint = computed(() => {
  const stats = statistics.value
  if (!stats) return ''
  const ordinary = Number(stats.ordinary_average_segment_cost)
  const templated = Number(stats.templated_average_segment_cost)
  if (!Number.isFinite(ordinary) || !Number.isFinite(templated) || ordinary <= 0) return ''
  const delta = ((ordinary - templated) / ordinary) * 100
  if (delta >= 0) return `Шаблонированный сегмент дешевле на ${delta.toFixed(0)} %`
  return `Шаблонированный сегмент дороже на ${Math.abs(delta).toFixed(0)} %`
})

const subscribersNote = computed(() => {
  const data = segmentation.value
  if (!data) return ''
  return (
    `Абонент — уникальный номер получателя с отправленными сегментами. ` +
    `Сообщения с нулевой длиной (ошибка отправки) не входят: ${integer(data.zero_segment_messages)}. ` +
    `Оператор абонента — по большинству его сообщений.`
  )
})

const subscriberDonut = computed(() =>
  (segmentation.value?.subscribers_by_operator ?? []).map((item) => ({
    name: item.operator,
    value: item.subscribers,
    color: operatorColor(item.operator),
  })),
)

const operatorCount = computed(() => segmentation.value?.subscribers_by_operator.length ?? 0)

const hasData = computed(() => Boolean(summary.value?.batch))

async function onBatch(event: Event): Promise<void> {
  await selectBatch((event.target as HTMLSelectElement).value)
}

async function refresh(): Promise<void> {
  await refreshAll()
}

onMounted(() => {
  if (!state.dashboard) void loadDashboard()
})
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy" :text="state.busyText" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Дашборд</h1>
        <div class="page-subtitle">
          <template v-if="summary?.batch">
            {{ batchName(summary.batch) }} · {{ period(summary.batch.period_from, summary.batch.period_to) }}
          </template>
          <template v-else>Загрузите статистику, чтобы увидеть сводку</template>
        </div>
      </div>
      <div class="toolbar">
        <select class="select" style="width: auto; max-width: 340px" :value="state.batchId" @change="onBatch">
          <option v-if="!state.batches.length" value="">Нет загрузок</option>
          <option v-for="batch in state.batches" :key="batch.id" :value="batch.id">
            {{ batchName(batch) }} · {{ batchPeriod(batch) }}
          </option>
        </select>
        <div class="segmented" role="group" aria-label="Вид дашборда">
          <button class="btn" :class="{ active: mode === 'overview' }" type="button" @click="mode = 'overview'">
            Обзор
          </button>
          <button class="btn" :class="{ active: mode === 'subscribers' }" type="button" @click="mode = 'subscribers'">
            Абоненты
          </button>
        </div>
        <button class="btn" type="button" :disabled="isBusy" @click="refresh">Обновить</button>
      </div>
    </header>

    <div v-if="!hasData" class="card empty">
      <h3>Данных пока нет</h3>
      <p class="muted">Импортируйте Excel-выгрузку статистики МТС-Маркетолога на вкладке «Импорт».</p>
      <RouterLink class="btn btn-primary" to="/import">Перейти к импорту</RouterLink>
    </div>

    <template v-else-if="summary">
      <section class="kpi-grid">
        <KpiCard
          label="Выгода шаблонов"
          :value="money(summary.total_monthly_net_benefit, 0)"
          :tone="Number(summary.total_monthly_net_benefit) >= 0 ? 'positive' : 'negative'"
          hint="в месяц, после вычета стоимости шаблонов"
        />
        <KpiCard label="Стоимость" :value="money(statistics?.cost ?? '0', 0)" :hint="`${integer(statistics?.segments ?? 0)} SMS-сегментов`" />
        <KpiCard label="Сообщений" :value="integer(statistics?.message_count ?? 0)" :hint="`${integer(statistics?.segments ?? 0)} сегментов`" />
        <KpiCard label="Доставлено" :value="integer(statistics?.delivered ?? 0)" :hint="share(statistics?.delivered_share ?? 0, 0) + ' от всех'" />
        <KpiCard label="Шаблонов" :value="integer(summary.template_count)" :hint="`активных: ${integer(summary.active_templates)}`" />
        <KpiCard label="Кандидатов" :value="integer(summary.candidates)" :hint="`выгодных: ${integer(summary.profitable_candidates)}`" tone="positive" />
      </section>

      <section class="card potential">
        <div class="potential-main">
          Потенциал роста: <strong>{{ money(summary.potential_benefit, 0) }}</strong> в месяц
        </div>
        <div class="potential-detail">
          внедрение кандидатов {{ money(summary.profitable_candidates_benefit, 0) }} ·
          удаление убыточных шаблонов {{ money(summary.loss_templates_benefit, 0) }}
        </div>
      </section>

      <template v-if="mode === 'overview'">
        <div class="dashboard-grid">
          <section class="card span-7 chart-card">
            <div class="card-header">
              <div>
                <div class="card-title">Динамика по дням</div>
                <div class="card-caption">отправленные SMS-сегменты по операторам</div>
              </div>
              <div class="card-caption">всего {{ integer(statistics?.segments ?? 0) }} сегментов</div>
            </div>
            <div class="chart-fit">
              <StackedBarChart :items="dailyItems" :height="230" />
            </div>
          </section>

          <section class="card span-5 structure-card">
            <div class="card-header">
              <div>
                <div class="card-title">Структура</div>
                <div class="card-caption">доли целого по сегментам и расходам</div>
              </div>
            </div>
            <div class="structure-fit">
              <StructureBars
                :ordinary-segment-share="statistics?.ordinary_segment_share ?? 0"
                :templated-segment-share="statistics?.templated_segment_share ?? 0"
                :ordinary-cost-share="costShares.ordinary"
                :templated-cost-share="costShares.templated"
              />
            </div>
            <div v-if="cheaperHint" class="insight">{{ cheaperHint }}</div>
            <p class="card-caption card-footer">
              Доли считаются по SMS-сегментам и фактическим списаниям периода.
            </p>
          </section>

          <section class="card span-7">
            <div class="card-header">
              <div>
                <div class="card-title">Классы сообщений</div>
                <div class="card-caption">доли и средняя стоимость — по SMS-сегментам</div>
              </div>
            </div>
            <div class="table-wrap fill">
              <table class="data">
                <thead>
                  <tr>
                    <th>Класс</th>
                    <th class="num">Сообщений</th>
                    <th class="num">Сегментов</th>
                    <th class="num">Счёт</th>
                    <th class="num">Средняя стоимость сегмента</th>
                    <th>Доля</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in classesRows" :key="row.name">
                    <td>
                      <span class="row" style="gap: 8px">
                        <i :style="{ background: row.tone, width: '9px', height: '9px', borderRadius: '3px', display: 'inline-block' }"></i>
                        {{ row.name }}
                      </span>
                    </td>
                    <td class="num">{{ integer(row.messages) }}</td>
                    <td class="num">{{ integer(row.segments) }}</td>
                    <td class="num">{{ money(row.cost) }}</td>
                    <td class="num">{{ money(row.average) }}</td>
                    <td style="min-width: 120px"><ShareMeter :value="row.shareValue" :color="row.tone" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="card span-5">
            <div class="card-header">
              <div>
                <div class="card-title">Операторы получателя</div>
                <div class="card-caption">топ-6 и «Другие»</div>
              </div>
            </div>
            <div class="table-wrap fill">
              <table class="data">
                <thead>
                  <tr>
                    <th>Оператор</th>
                    <th class="num">Сообщений</th>
                    <th class="num">Сегментов</th>
                    <th class="num">Счёт</th>
                    <th>Доля</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in topOperators" :key="row.name">
                    <td>
                      <span class="row" style="gap: 8px">
                        <i :style="{ background: row.color, width: '9px', height: '9px', borderRadius: '50%', display: 'inline-block' }"></i>
                        {{ row.name }}
                      </span>
                    </td>
                    <td class="num">{{ integer(row.messages) }}</td>
                    <td class="num">{{ integer(row.segments) }}</td>
                    <td class="num">{{ money(row.cost, 0) }}</td>
                    <td style="min-width: 110px"><ShareMeter :value="row.shareValue" :color="row.color" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="concentration" class="card-caption card-footer">{{ concentration }}</div>
          </section>
        </div>
      </template>

      <template v-else>
        <section class="kpi-grid subscribers">
          <KpiCard
            label="Уникальных абонентов"
            :value="integer(segmentation?.subscribers ?? 0)"
            :hint="`операторов: ${integer(operatorCount)}`"
          />
          <KpiCard
            label="Сегментов на абонента"
            :value="(segmentation?.average_subscriber_segments ?? 0).toFixed(1)"
            :hint="`${integer(segmentation?.subscriber_segments ?? 0)} сегментов`"
          />
          <KpiCard
            label="Сообщений на абонента"
            :value="(segmentation?.average_subscriber_messages ?? 0).toFixed(1)"
            :hint="`${integer(segmentation?.subscriber_messages ?? 0)} сообщений`"
          />
        </section>

        <div class="audience-grid">
          <section class="card audience-card">
            <div class="card-header">
              <div class="card-title">Абоненты по числу сегментов</div>
            </div>
            <div class="chart-fit">
              <DistributionChart :bars="groupBuckets(segmentation?.subscribers_by_segments ?? [])" :height="200" color="#0d9488" />
            </div>
          </section>
          <section class="card audience-card">
            <div class="card-header">
              <div class="card-title">Абоненты по операторам</div>
            </div>
            <div class="chart-fit">
              <DonutChart :slices="subscriberDonut" :height="210" :center-label="integer(segmentation?.subscribers ?? 0)" />
            </div>
          </section>
          <section class="card audience-card">
            <div class="card-header">
              <div class="card-title">Сообщения по числу сегментов</div>
            </div>
            <div class="chart-fit">
              <DistributionChart :bars="groupBuckets(segmentation?.messages_by_segments ?? [])" :height="200" color="#b45309" />
            </div>
          </section>
        </div>
        <p class="card-caption audience-note">{{ subscribersNote }}</p>
      </template>

      <details v-if="summary.warnings.length" class="card warnings">
        <summary>▸ Предупреждения и допущения · {{ summary.warnings.length }}</summary>
        <ul>
          <li v-for="warning in summary.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface);
}

.segmented .btn {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 8px 14px;
  color: var(--text-muted);
}

.segmented .btn.active {
  background: var(--selection);
  color: var(--text);
}

.potential {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  background: linear-gradient(90deg, color-mix(in srgb, var(--positive) 8%, var(--surface)), var(--surface) 60%);
}

.potential-main {
  font-size: 16px;
}

.potential-main strong {
  color: var(--positive);
  font-size: 20px;
}

.potential-detail {
  color: var(--text-muted);
  font-size: 12px;
}

.insight {
  margin-top: calc(var(--space) * 1.5);
  padding: 8px 10px;
  border-radius: var(--radius);
  background: var(--surface-alt);
  font-size: 12px;
  color: var(--text-muted);
}

.structure-fit {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.audience-note {
  margin: 0;
  padding: 0 2px;
}
</style>
