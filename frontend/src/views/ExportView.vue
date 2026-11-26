<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import BusyOverlay from '../components/BusyOverlay.vue'
import { date, integer, money, period, share } from '../format'
import {
  isBusy,
  loadDashboard,
  reportError,
  selectBatch,
  state,
} from '../store'

const exporting = ref(false)
const done = ref('')

const summary = computed(() => state.dashboard)
const batch = computed(() => summary.value?.batch ?? null)
const statistics = computed(() => summary.value?.statistics ?? null)

async function onBatch(event: Event): Promise<void> {
  done.value = ''
  await selectBatch((event.target as HTMLSelectElement).value)
}

async function download(): Promise<void> {
  if (!state.batchId || !batch.value) return
  exporting.value = true
  done.value = ''
  try {
    const blob = await api.exportReport(state.batchId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const base = batch.value.source_name.replace(/\.[^.]+$/, '')
    link.href = url
    link.download = `mts-report-${base}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    done.value = 'Отчёт сформирован и скачан'
  } catch (error) {
    reportError(error)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy || exporting" text="Формирование Excel-отчёта…" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Экспорт</h1>
        <div class="page-subtitle">Excel-отчёт по загрузке, анализу и кандидатам</div>
      </div>
      <div class="toolbar">
        <select class="select" style="width: auto; max-width: 360px" :value="state.batchId" @change="onBatch">
          <option v-if="!state.batches.length" value="">Нет загрузок</option>
          <option v-for="item in state.batches" :key="item.id" :value="item.id">
            {{ item.source_name }} · {{ date(item.period_from) }} — {{ date(item.period_to) }}
          </option>
        </select>
        <button class="btn btn-primary" type="button" :disabled="!batch || exporting" @click="download">
          Скачать Excel
        </button>
      </div>
    </header>

    <div v-if="!batch" class="card empty">
      <h3>Нет данных для отчёта</h3>
      <p class="muted">Сначала импортируйте статистику и шаблоны.</p>
      <RouterLink class="btn btn-primary" to="/import">Перейти к импорту</RouterLink>
    </div>

    <template v-else>
      <div class="columns-3-2">
        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Содержимое отчёта</div>
              <div class="card-caption">{{ batch.source_name }} · {{ period(batch.period_from, batch.period_to) }}</div>
            </div>
          </div>
          <ul class="report-list">
            <li>
              <strong>Сводка</strong>
              <span>период, объёмы, стоимость, доставка, методика расчёта и предупреждения</span>
            </li>
            <li>
              <strong>Классы сообщений</strong>
              <span>обычные и шаблонированные SMS: сообщения, сегменты, счёт, средние ставки</span>
            </li>
            <li>
              <strong>Шаблоны</strong>
              <span>подпадание, срабатывание, разбивка по операторам, фактическая и месячная выгода</span>
            </li>
            <li>
              <strong>Кандидаты</strong>
              <span>сгенерированные шаблоны, объём, экономия, уверенность и окупаемость</span>
            </li>
            <li>
              <strong>Операторы и абоненты</strong>
              <span>сегменты и счёт по операторам, распределения по числу сегментов</span>
            </li>
            <li>
              <strong>Графики</strong>
              <span>диаграммы вкладок: структура, операторы, распределения, дневные ряды</span>
            </li>
          </ul>
          <p v-if="done" class="badge badge-positive" style="margin-top: 12px">{{ done }}</p>
          <p class="field-hint" style="margin-top: 10px">
            Если анализ ещё не выполнялся, отчёт выйдет без шаблонов и кандидатов —
            выполните расчёт на вкладках «Шаблоны» или «Кандидаты».
          </p>
        </section>

        <section class="card">
          <div class="card-header">
            <div class="card-title">Загрузка</div>
          </div>
          <div class="details-grid">
            <span>Файл</span><strong>{{ batch.source_name }}</strong>
            <span>Импортирован</span><strong>{{ date(batch.imported_at) }}</strong>
            <span>Период</span><strong>{{ period(batch.period_from, batch.period_to) }}</strong>
            <span>Сообщений</span><strong>{{ integer(statistics?.message_count ?? 0) }}</strong>
            <span>Сегментов</span><strong>{{ integer(statistics?.segments ?? 0) }}</strong>
            <span>Стоимость</span><strong>{{ money(statistics?.cost ?? '0') }}</strong>
            <span>Доставлено</span><strong>{{ share(statistics?.delivered_share ?? 0) }}</strong>
            <span>Шаблонов</span><strong>{{ integer(summary?.template_count ?? 0) }}</strong>
            <span>Кандидатов</span><strong>{{ integer(summary?.candidates ?? 0) }}</strong>
            <span>Выгода шаблонов/мес</span>
            <strong :class="Number(summary?.total_monthly_net_benefit ?? 0) >= 0 ? 'positive' : 'negative'">
              {{ money(summary?.total_monthly_net_benefit ?? '0') }}
            </strong>
          </div>
          <div class="row card-footer" style="margin-top: 16px">
            <button class="btn" type="button" @click="loadDashboard(state.batchId)">Обновить данные</button>
            <RouterLink class="btn" to="/templates">К шаблонам</RouterLink>
          </div>
        </section>
      </div>

      <details v-if="summary?.warnings.length" class="card warnings">
        <summary>▸ Предупреждения и допущения · {{ summary.warnings.length }}</summary>
        <ul>
          <li v-for="warning in summary.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<style scoped>
.report-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.report-list li {
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
}

.report-list li:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.report-list span {
  color: var(--text-muted);
}

.details-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 7px 14px;
  font-size: 12px;
  align-items: baseline;
}

.details-grid span {
  color: var(--text-muted);
}

@media (max-width: 620px) {
  .report-list li {
    grid-template-columns: 1fr;
    gap: 3px;
  }
}
</style>
