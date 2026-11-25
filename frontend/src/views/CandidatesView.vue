<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import MatchedMessagesDialog from '../components/MatchedMessagesDialog.vue'
import SegmentChart from '../components/SegmentChart.vue'
import { date, integer, money, period, share } from '../format'
import { analyze, benefitClass, isBusy, selectBatch, state } from '../store'
import type { Candidate, DaySegments } from '../types'

const selectedId = ref('')
const filter = ref('')
const templatedOnly = ref(false)
const dialog = ref<{ id: string; heading: string; text: string } | null>(null)

const analysis = computed(() => state.analysis)

const filtered = computed(() => {
  const query = filter.value.trim().toLowerCase()
  const rows = analysis.value?.candidates ?? []
  if (!query) return rows
  return rows.filter((candidate) =>
    [candidate.template_text, candidate.senders.join(' '), candidate.operators.join(' ')].some(
      (value) => value.toLowerCase().includes(query),
    ),
  )
})

const selected = computed(
  () => analysis.value?.candidates.find((item) => item.candidate_id === selectedId.value) ?? null,
)

const profitableTotal = computed(() =>
  (analysis.value?.candidates ?? []).reduce(
    (sum, candidate) => sum + Math.max(0, Number(candidate.net_monthly)),
    0,
  ),
)

const chartBase = computed<DaySegments[]>(() => {
  if (!analysis.value) return []
  if (templatedOnly.value) {
    const totals = new Map<string, number>()
    for (const item of analysis.value.daily_templated_segments) totals.set(item.day, item.segments)
    for (const item of selected.value?.daily_segments ?? []) {
      totals.set(item.day, (totals.get(item.day) ?? 0) + item.segments)
    }
    return [...totals.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, segments]) => ({ day, segments }))
  }
  if (state.dashboard?.batch?.id === analysis.value.batch_id) {
    return state.dashboard.daily_segments.map((item) => ({ day: item.day, segments: item.segments }))
  }
  return analysis.value.daily_total_segments
})

const chartCaption = computed(() => {
  if (!selected.value) return ''
  const base = chartBase.value.reduce((sum, item) => sum + item.segments, 0)
  return templatedOnly.value
    ? `кандидат: ${integer(selected.value.segments)} из ${integer(base)} шаблонированных сегментов`
    : `кандидат: ${integer(selected.value.segments)} из ${integer(base)} сегментов`
})

const confidenceLabel = computed(() => {
  if (!selected.value) return ''
  const labels: Record<string, string> = {
    auto_validated: 'проверен автоматически',
    needs_human_approval: 'нужно подтверждение человека',
    warning_saved: 'сохранён с предупреждением',
    rejected: 'отклонён',
  }
  return labels[selected.value.status] ?? selected.value.status
})

function openMessages(candidate: Candidate): void {
  dialog.value = {
    id: candidate.candidate_id,
    heading: 'Сообщения кандидата',
    text: candidate.template_text,
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
    if (!view.candidates.some((item) => item.candidate_id === selectedId.value)) {
      selectedId.value = view.candidates[0]?.candidate_id ?? ''
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
        <h1 class="page-title">Кандидаты</h1>
        <div class="page-subtitle">
          Однотипные незашаблонированные сообщения и выгода от регистрации шаблона
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
      <p class="muted">Импортируйте выгрузку, чтобы найти группы однотипных сообщений.</p>
      <RouterLink class="btn btn-primary" to="/import">Перейти к импорту</RouterLink>
    </div>

    <div v-else-if="!analysis" class="card empty">
      <h3>Поиск кандидатов ещё не выполнялся</h3>
      <p class="muted">Запустите анализ: сигнатурная группировка найдёт группы и предложит шаблоны.</p>
      <button class="btn btn-primary" type="button" @click="runAnalysis()">Найти кандидатов</button>
    </div>

    <template v-else>
      <section class="card">
        <div class="table-wrap" style="max-height: 420px">
          <table class="data">
            <thead>
              <tr>
                <th style="min-width: 360px">Шаблон-кандидат</th>
                <th class="num">Сообщений</th>
                <th class="num">Сегментов</th>
                <th class="num">Стоимость</th>
                <th class="num">Если шаблон</th>
                <th class="num">Выгода/мес</th>
                <th class="num">Уверенность</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="candidate in filtered"
                :key="candidate.candidate_id"
                :class="[benefitClass(candidate.net_monthly), { 'selected-row': candidate.candidate_id === selectedId }]"
                @click="selectedId = candidate.candidate_id"
              >
                <td>
                  <button class="link-button" type="button" :title="candidate.template_text" @click.stop="openMessages(candidate)">
                    {{ candidate.template_text }}
                  </button>
                </td>
                <td class="num">{{ integer(candidate.messages) }}</td>
                <td class="num">{{ integer(candidate.segments) }}</td>
                <td class="num" :title="`Фактически за период: ${money(candidate.actual_cost)}`">
                  {{ money(candidate.monthly_actual_cost, 0) }}
                </td>
                <td class="num" :title="`Фактически за период: ${money(candidate.templated_cost)}`">
                  {{ money(candidate.monthly_templated_cost, 0) }}
                </td>
                <td class="num">
                  <strong :class="Number(candidate.net_monthly) >= 0 ? 'positive' : 'negative'">
                    {{ money(candidate.net_monthly, 0) }}
                  </strong>
                </td>
                <td class="num">{{ share(candidate.confidence, 0) }}</td>
                <td>
                  <span class="badge" :title="candidate.status">{{ candidate.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!filtered.length" class="empty">
            Кандидатов не найдено: возможно, все однотипные сообщения уже покрыты шаблонами.
          </div>
        </div>
      </section>

      <div class="lower-grid">
        <section class="card">
          <div class="benefit-total">
            <div class="benefit-total-value" :class="profitableTotal > 0 ? 'positive' : ''">
              {{ money(profitableTotal, 0) }}
            </div>
            <div class="benefit-total-label">Выгода в месяц от внедрения выгодных кандидатов</div>
          </div>

          <div v-if="selected" class="details">
            <div class="details-title">Выбранный кандидат</div>
            <p class="tiny muted">{{ period(selected.period_from, selected.period_to) }}</p>
            <div class="details-grid">
              <span>Сообщений</span><strong>{{ integer(selected.messages) }}</strong>
              <span>Сегментов</span><strong>{{ integer(selected.segments) }}</strong>
              <span>Стоимость/мес</span><strong>{{ money(selected.monthly_actual_cost) }}</strong>
              <span>Если шаблон/мес</span><strong>{{ money(selected.monthly_templated_cost) }}</strong>
              <span>Экономия/мес</span><strong>{{ money(selected.monthly_saving) }}</strong>
              <span>Шаблон/мес</span><strong>{{ money(selected.template_fee) }}</strong>
              <span>Выгода/мес</span>
              <strong :class="Number(selected.net_monthly) >= 0 ? 'positive' : 'negative'">
                {{ money(selected.net_monthly) }}
              </strong>
              <span>Уверенность</span><strong>{{ share(selected.confidence, 0) }} · {{ confidenceLabel }}</strong>
              <span>Покрытие</span><strong>{{ share(selected.coverage, 0) }}</strong>
              <span>Операторы</span><strong>{{ selected.operators.length ? selected.operators.join(', ') : 'все' }}</strong>
              <span>Чужие совпадения</span><strong>{{ integer(selected.foreign_matches) }}</strong>
            </div>

            <div v-if="selected.warnings.length" class="details-block">
              <div class="details-title">Предупреждения</div>
              <ul class="tiny">
                <li v-for="warning in selected.warnings" :key="warning">{{ warning }}</li>
              </ul>
            </div>
            <div v-if="selected.examples.length" class="details-block">
              <div class="details-title">Примеры сообщений</div>
              <ul class="examples">
                <li v-for="example in selected.examples" :key="example">{{ example }}</li>
              </ul>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Сегменты по дням</div>
              <div class="card-caption">выбранный кандидат</div>
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
            matched-label="Сообщения кандидата"
            :series-label="templatedOnly ? 'Остальной шаблонированный трафик' : 'Остальной трафик'"
            :height="230"
          />
          <div v-else class="empty">Выберите кандидата в таблице</div>
        </section>
      </div>

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
      target-type="candidate"
      :target-id="dialog.id"
      :heading="dialog.heading"
      :text="dialog.text"
      @close="dialog = null"
    />
  </div>
</template>

<style scoped>
.lower-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: calc(var(--space) * 2);
  align-items: start;
}

.benefit-total {
  padding: calc(var(--space) * 1.5) 0 calc(var(--space) * 1.5);
  border-bottom: var(--border-width) solid var(--border);
  margin-bottom: calc(var(--space) * 1.5);
}

.benefit-total-value {
  font-family: var(--font-heading);
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.benefit-total-label {
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 6px;
}

.details-title {
  font-weight: 700;
  font-size: 12px;
  margin-bottom: 6px;
}

.details-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 14px;
  font-size: 12px;
  align-items: baseline;
}

.details-grid span {
  color: var(--text-muted);
}

.details-block {
  margin-top: calc(var(--space) * 1.5);
}

.details-block ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.5;
}

.examples li {
  margin-bottom: 4px;
  overflow-wrap: anywhere;
}

@media (max-width: 1180px) {
  .lower-grid {
    grid-template-columns: 1fr;
  }
}
</style>
