<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import KpiCard from '../components/KpiCard.vue'
import MatchedMessagesDialog from '../components/MatchedMessagesDialog.vue'
import { batchName, batchPeriod, integer, money, moneyValue, period } from '../format'
import { isBusy, loadActionCenter, selectBatch, state } from '../store'
import type { Action, ActionItem, ActionKind } from '../types'

type KindFilter = 'all' | ActionKind

interface DialogState {
  targetType: 'template' | 'unmatched'
  targetId: string
  heading: string
  text: string
  operator: string | null
  untriggeredOnly: boolean
}

const kindFilter = ref<KindFilter>('all')
const query = ref('')
const dialog = ref<DialogState | null>(null)

const center = computed(() => state.actionCenter)
const items = computed(() => center.value?.items ?? [])

const kindLabels: Record<ActionKind, string> = {
  loss_template: 'Убыточный шаблон',
  unworking_template: 'Неработающий',
  profitable_candidate: 'Выгодный кандидат',
  untriggered: 'Срабатывание ниже 100 %',
  unmatched_templated: 'Шаблонировано без шаблона',
}

const actionLabels: Record<Action, string> = {
  delete: 'Удалить',
  add: 'Добавить',
}

const counts = computed<Record<ActionKind, number>>(() => {
  const result: Record<ActionKind, number> = {
    loss_template: 0,
    unworking_template: 0,
    profitable_candidate: 0,
    untriggered: 0,
    unmatched_templated: 0,
  }
  for (const item of items.value) result[item.kind] += 1
  return result
})

const filters = computed(() =>
  (
    [
      'all',
      'loss_template',
      'unworking_template',
      'profitable_candidate',
      'untriggered',
      'unmatched_templated',
    ] as KindFilter[]
  ).map((kind) => ({
    kind,
    label: kind === 'all' ? 'Все' : kindLabels[kind],
    count: kind === 'all' ? items.value.length : counts.value[kind],
  })),
)

const filtered = computed(() => {
  const text = query.value.trim().toLowerCase()
  return items.value.filter((item) => {
    if (kindFilter.value !== 'all' && item.kind !== kindFilter.value) return false
    if (!text) return true
    return [item.title, item.subject, item.operator ?? '', item.template_name, item.detail].some(
      (value) => value.toLowerCase().includes(text),
    )
  })
})

const lossTemplateTotal = computed(() =>
  items.value
    .filter((item) => item.kind === 'loss_template' || item.kind === 'unworking_template')
    .reduce((sum, item) => sum + moneyValue(item.monthly_loss), 0),
)

const hasBatch = computed(() => Boolean(state.batchId))
const totalLoss = computed(() => moneyValue(center.value?.total_monthly_loss ?? 0))
const totalBenefit = computed(() => moneyValue(center.value?.total_monthly_benefit ?? 0))

function lossText(item: ActionItem): string {
  if (item.kind === 'unmatched_templated' || moneyValue(item.monthly_loss) === 0) return '—'
  return money(item.monthly_loss, 0)
}

function benefitText(item: ActionItem): string {
  return moneyValue(item.monthly_benefit) > 0 ? money(item.monthly_benefit, 0) : '—'
}

const methodology = computed(() => {
  if (!center.value) return ''
  const parts = [
    center.value.observed_templated_rate
      ? `шаблонированный сегмент — ${money(center.value.observed_templated_rate)}`
      : 'наблюдаемая ставка шаблонированных SMS не определена',
    center.value.observed_ordinary_rate
      ? `обычный сегмент — ${money(center.value.observed_ordinary_rate)}`
      : 'наблюдаемая ставка обычных SMS не определена',
  ]
  if (center.value.is_partial_period) {
    parts.push(`неполный период смоделирован до 30 дней (×${center.value.monthly_factor.toFixed(2)})`)
  } else {
    parts.push('период полный, суммы не масштабируются')
  }
  return `Методика: потери — фактическая стоимость минус оценка по шаблонированной ставке; выгода — месячная выгода кандидатов после вычета стоимости шаблона; ${parts.join('; ')}.`
})

function severityLabel(item: ActionItem): string {
  if (item.severity >= 3) return 'Критично'
  if (item.severity === 2) return 'Высокий'
  if (item.severity === 1) return 'Средний'
  return 'Инфо'
}

function severityClass(item: ActionItem): string {
  return `sev-${item.severity}`
}

function showMessages(item: ActionItem): void {
  if (item.kind === 'unmatched_templated' || item.drill_down === 'unmatched_templated') {
    dialog.value = {
      targetType: 'unmatched',
      targetId: '',
      heading: item.title,
      text: '',
      operator: null,
      untriggeredOnly: false,
    }
    return
  }
  if (!item.template_id) return
  dialog.value = {
    targetType: 'template',
    targetId: item.template_id,
    heading: item.template_name || item.subject || item.title,
    text: item.subject,
    operator: item.operator,
    untriggeredOnly: item.kind === 'untriggered',
  }
}

async function refresh(): Promise<void> {
  await loadActionCenter(true)
}

async function onBatch(event: Event): Promise<void> {
  await selectBatch((event.target as HTMLSelectElement).value)
}

onMounted(() => {
  if (hasBatch.value) void loadActionCenter()
})

watch(
  () => state.batchId,
  (batchId) => {
    if (batchId) void loadActionCenter()
  },
)
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy" :text="state.busyText" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Центр действий</h1>
        <div class="page-subtitle">
          <template v-if="center">
            Где теряются деньги, что сделать первым и какие возможности есть ·
            {{ period(center.period_from, center.period_to) }}
          </template>
          <template v-else>Рабочий список проблем и возможностей по выбранной загрузке</template>
        </div>
      </div>
      <div class="toolbar">
        <select class="select" style="width: auto; max-width: 340px" :value="state.batchId" @change="onBatch">
          <option v-if="!state.batches.length" value="">Нет загрузок</option>
          <option v-for="batch in state.batches" :key="batch.id" :value="batch.id">
            {{ batchName(batch) }} · {{ batchPeriod(batch) }}
          </option>
        </select>
        <button class="btn" type="button" :disabled="isBusy || !hasBatch" @click="refresh">
          Пересчитать
        </button>
      </div>
    </header>

    <div v-if="!hasBatch" class="card empty">
      <h3>Данных пока нет</h3>
      <p class="muted">Импортируйте Excel-выгрузку статистики на вкладке «Импорт».</p>
      <RouterLink class="btn btn-primary" to="/import">Перейти к импорту</RouterLink>
    </div>

    <div v-else-if="!center && !isBusy" class="card empty">
      <p class="muted">Не удалось собрать центр действий. Попробуйте пересчитать.</p>
      <button class="btn" type="button" @click="refresh">Пересчитать</button>
    </div>

    <template v-else-if="center">
      <section class="action-kpis">
        <KpiCard
          label="Потери в месяц"
          :value="money(center.total_monthly_loss, 0)"
          :tone="totalLoss > 0 ? 'negative' : 'positive'"
          hint="оценка по шаблонированной ставке"
        />
        <KpiCard
          label="Выгода действий"
          :value="money(center.total_monthly_benefit, 0)"
          :tone="totalBenefit > 0 ? 'positive' : 'default'"
          :hint="`${integer(center.profitable_candidates)} кандидатов на добавление`"
        />
        <KpiCard
          label="Срабатывание ниже 100 %"
          :value="money(center.untriggered_loss, 0)"
          :tone="moneyValue(center.untriggered_loss) > 0 ? 'negative' : 'default'"
          :hint="`${integer(center.untriggered_messages)} сообщений`"
        />
        <KpiCard
          label="Убыточные шаблоны"
          :value="integer(center.loss_templates)"
          :tone="center.loss_templates > 0 ? 'negative' : 'default'"
          :hint="`${money(lossTemplateTotal, 0)} платы в месяц`"
        />
      </section>

      <section v-if="center.unmatched_templated_messages > 0" class="card unmatched-banner">
        <div>
          <div class="card-title">Шаблонировано без шаблона</div>
          <div class="card-caption">
            {{ integer(center.unmatched_templated_messages) }} сообщений ·
            {{ integer(center.unmatched_templated_segments) }} сегментов оплачены как
            шаблонированные, но не сопоставились ни с одним шаблоном. Оплачено за период:
            {{ money(center.unmatched_templated_cost) }}.
          </div>
        </div>
        <button
          class="btn"
          type="button"
          @click="
            dialog = {
              targetType: 'unmatched',
              targetId: '',
              heading: 'Сообщения без зарегистрированного шаблона',
              text: '',
              operator: null,
              untriggeredOnly: false,
            }
          "
        >
          Показать сообщения
        </button>
      </section>

      <section class="card table-card">
        <div class="card-header action-table-header">
          <div>
            <div class="card-title">Проблемы и возможности по приоритету</div>
            <div class="card-caption">
              {{ integer(filtered.length) }} из {{ integer(items.length) }} · сортировка по эффекту
            </div>
          </div>
          <input
            v-model="query"
            class="input"
            type="search"
            placeholder="Поиск по шаблону, оператору, проблеме"
            style="max-width: 340px"
          />
        </div>

        <div class="chips" role="group" aria-label="Фильтр по типу проблемы">
          <button
            v-for="filter in filters"
            :key="filter.kind"
            class="chip"
            :class="{ active: kindFilter === filter.kind }"
            type="button"
            @click="kindFilter = filter.kind"
          >
            {{ filter.label }}
            <span class="chip-count">{{ integer(filter.count) }}</span>
          </button>
        </div>

        <div v-if="!filtered.length" class="empty">
          По этому фильтру пунктов нет — значит, по выбранной загрузке всё в порядке.
        </div>
        <div v-else class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Приоритет</th>
                <th>Проблема / возможность</th>
                <th>Действие</th>
                <th>Шаблон / объект</th>
                <th>Оператор</th>
                <th class="num">Сообщений</th>
                <th class="num">Сегментов</th>
                <th class="num">Потери/мес</th>
                <th class="num">Выгода/мес</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filtered" :key="item.key">
                <td>
                  <span class="badge" :class="severityClass(item)">{{ severityLabel(item) }}</span>
                </td>
                <td>
                  <div class="cell-clamp" :title="`${item.title}. ${item.detail} ${item.recommendation}`">
                    {{ item.title }}
                  </div>
                  <div class="tiny muted cell-clamp" :title="item.recommendation">
                    {{ item.recommendation }}
                  </div>
                </td>
                <td>
                  <span v-if="item.action" class="action-badge" :class="`act-${item.action}`">
                    {{ actionLabels[item.action] }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
                <td>
                  <div class="cell-clamp" :title="item.subject">{{ item.subject }}</div>
                </td>
                <td>{{ item.operator || '—' }}</td>
                <td class="num">{{ integer(item.messages) }}</td>
                <td class="num">{{ integer(item.segments) }}</td>
                <td
                  class="num"
                  :class="{
                    negative: moneyValue(item.monthly_loss) > 0,
                    muted: item.kind === 'unmatched_templated',
                  }"
                  :title="item.detail"
                >
                  {{ item.kind === 'unmatched_templated' ? 'инфо' : lossText(item) }}
                </td>
                <td
                  class="num"
                  :class="{ positive: moneyValue(item.monthly_benefit) > 0 }"
                  :title="item.detail"
                >
                  {{ benefitText(item) }}
                </td>
                <td>
                  <button
                    v-if="item.drill_down"
                    class="btn btn-ghost action-link"
                    type="button"
                    @click="showMessages(item)"
                  >
                    Сообщения
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="card-caption card-footer">{{ methodology }}</p>
      </section>

      <details v-if="center.warnings.length" class="card warnings">
        <summary>▸ Предупреждения и допущения · {{ center.warnings.length }}</summary>
        <ul>
          <li v-for="warning in center.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </details>
    </template>

    <MatchedMessagesDialog
      v-if="dialog"
      :batch-id="state.batchId"
      :target-type="dialog.targetType"
      :target-id="dialog.targetId"
      :heading="dialog.heading"
      :text="dialog.text"
      :operator="dialog.operator"
      :untriggered-only="dialog.untriggeredOnly"
      @close="dialog = null"
    />
  </div>
</template>

<style scoped>
.action-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: calc(var(--space) * 1.5);
}

.unmatched-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: calc(var(--space) * 2);
  flex-wrap: wrap;
  border-left: 3px solid var(--warning);
}

.unmatched-banner > div {
  min-width: 0;
}

.action-table-header {
  align-items: flex-end;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  border: var(--border-width) solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.chip:hover {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
  color: var(--text);
}

.chip.active {
  border-color: var(--accent);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 9%, var(--surface));
}

.chip-count {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.action-link {
  padding: 2px 6px;
  white-space: nowrap;
}

.badge.sev-1 {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 12%, var(--surface));
  border-color: color-mix(in srgb, var(--warning) 30%, var(--border));
}

.badge.sev-2 {
  color: var(--negative);
  background: color-mix(in srgb, var(--negative) 10%, var(--surface));
  border-color: color-mix(in srgb, var(--negative) 26%, var(--border));
}

.badge.sev-3 {
  color: var(--surface);
  background: var(--negative);
  border-color: var(--negative);
}

.badge.sev-0 {
  color: var(--text-muted);
}

.action-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  border: var(--border-width) solid var(--border);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.action-badge.act-delete {
  color: var(--negative);
  border-color: color-mix(in srgb, var(--negative) 30%, var(--border));
  background: color-mix(in srgb, var(--negative) 10%, var(--surface));
}

.action-badge.act-add {
  color: var(--positive);
  border-color: color-mix(in srgb, var(--positive) 30%, var(--border));
  background: color-mix(in srgb, var(--positive) 10%, var(--surface));
}

@media (max-width: 1100px) {
  .action-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
