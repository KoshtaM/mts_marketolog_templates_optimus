<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import BusyOverlay from '../components/BusyOverlay.vue'
import { money } from '../format'
import {
  isBusy,
  resetToSystemTheme,
  saveSettings,
  setTheme,
  state,
} from '../store'
import type { AppSettings, Theme } from '../types'

const tab = ref<'general' | 'appearance' | 'advanced'>('general')
const saved = ref(false)

interface FormState {
  template_fee: string
  min_support: number
  min_cluster_segments: number
  min_text_length: number
  max_foreign_matches: number
  max_w_words: number
  max_d_words: number
  max_word_slots_per_merge: number
  max_literal_cardinality: number
  max_tail_depth: number
  punctuation_policy: string
  fold_yo: boolean
  fold_homoglyphs: boolean
  sender_case_sensitive: boolean
  baseline_mode: string
  delivered_only: boolean
  benefit_thresholds: string[]
}

const form = reactive<FormState>({
  template_fee: '2000',
  min_support: 3,
  min_cluster_segments: 3,
  min_text_length: 0,
  max_foreign_matches: 0,
  max_w_words: 3,
  max_d_words: 3,
  max_word_slots_per_merge: 3,
  max_literal_cardinality: 3,
  max_tail_depth: 3,
  punctuation_policy: 'delete',
  fold_yo: false,
  fold_homoglyphs: false,
  sender_case_sensitive: false,
  baseline_mode: 'observed',
  delivered_only: false,
  benefit_thresholds: ['1', '3000', '10000', '30000', '100000'],
})

function sync(settings: AppSettings | null): void {
  if (!settings) return
  form.template_fee = settings.template_fee
  form.min_support = settings.min_support
  form.min_cluster_segments = settings.min_cluster_segments
  form.min_text_length = settings.min_text_length
  form.max_foreign_matches = settings.max_foreign_matches
  form.max_w_words = settings.max_w_words
  form.max_d_words = settings.max_d_words
  form.max_word_slots_per_merge = settings.max_word_slots_per_merge
  form.max_literal_cardinality = settings.max_literal_cardinality
  form.max_tail_depth = settings.max_tail_depth
  form.punctuation_policy = settings.punctuation_policy
  form.fold_yo = settings.fold_yo
  form.fold_homoglyphs = settings.fold_homoglyphs
  form.sender_case_sensitive = settings.sender_case_sensitive
  form.baseline_mode = settings.baseline_mode
  form.delivered_only = settings.delivered_only
  form.benefit_thresholds = [...settings.benefit_thresholds]
}

watch(() => state.settings, sync, { immediate: true })

const punctuationOptions = [
  { value: 'delete', label: 'Удалять пунктуацию (по умолчанию)' },
  { value: 'space', label: 'Заменять пробелом' },
  { value: 'keep', label: 'Учитывать как есть' },
]

const baselineOptions = [
  { value: 'observed', label: 'Наблюдаемая ставка периода' },
  { value: 'catalog', label: 'Каталог тарифов' },
]

async function save(): Promise<void> {
  saved.value = false
  const result = await saveSettings({
    template_fee: form.template_fee.replace(',', '.'),
    min_support: Number(form.min_support),
    min_cluster_segments: Number(form.min_cluster_segments),
    min_text_length: Number(form.min_text_length),
    max_foreign_matches: Number(form.max_foreign_matches),
    max_w_words: Number(form.max_w_words),
    max_d_words: Number(form.max_d_words),
    max_word_slots_per_merge: Number(form.max_word_slots_per_merge),
    max_literal_cardinality: Number(form.max_literal_cardinality),
    max_tail_depth: Number(form.max_tail_depth),
    punctuation_policy: form.punctuation_policy,
    fold_yo: form.fold_yo,
    fold_homoglyphs: form.fold_homoglyphs,
    sender_case_sensitive: form.sender_case_sensitive,
    baseline_mode: form.baseline_mode,
    delivered_only: form.delivered_only,
    benefit_thresholds: form.benefit_thresholds,
  })
  saved.value = result !== null
}

function chooseTheme(theme: Theme): void {
  void setTheme(theme.id)
}
</script>

<template>
  <div class="page" style="position: relative">
    <BusyOverlay v-if="isBusy" :text="state.busyText" />

    <header class="page-header">
      <div>
        <h1 class="page-title">Настройки</h1>
        <div class="page-subtitle">Параметры анализа, пороги выгоды и оформление</div>
      </div>
      <div class="tabs">
        <button class="btn" :class="{ active: tab === 'general' }" type="button" @click="tab = 'general'">
          Общие
        </button>
        <button class="btn" :class="{ active: tab === 'appearance' }" type="button" @click="tab = 'appearance'">
          Внешний вид
        </button>
        <button class="btn" :class="{ active: tab === 'advanced' }" type="button" @click="tab = 'advanced'">
          Дополнительно
        </button>
      </div>
    </header>

    <template v-if="tab === 'general'">
      <div class="settings-grid">
        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Экономика</div>
              <div class="card-caption">стоимость шаблона, baseline и пороги</div>
            </div>
          </div>
          <div class="form-grid">
            <label class="field">
              <span class="field-label">Стоимость шаблона, ₽/мес</span>
              <input v-model="form.template_fee" class="input" inputmode="decimal" />
              <span class="field-hint">Взимается один раз за шаблон, независимо от операторов</span>
            </label>
            <label class="field">
              <span class="field-label">Модель baseline</span>
              <select v-model="form.baseline_mode" class="select">
                <option v-for="option in baselineOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <div class="field" style="grid-column: 1 / -1">
              <span class="field-label">Пороги выгоды, ₽/мес (пять уровней по возрастанию)</span>
              <div class="thresholds">
                <input
                  v-for="(_, index) in form.benefit_thresholds"
                  :key="index"
                  v-model="form.benefit_thresholds[index]"
                  class="input"
                  inputmode="decimal"
                  :aria-label="`Порог ${index + 1}`"
                />
              </div>
              <span class="field-hint">
                Строки таблиц окрашиваются по месячной выгоде; убыток — красным.
              </span>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Поиск кандидатов</div>
              <div class="card-caption">сигнатурная группировка без fuzzy и ML</div>
            </div>
          </div>
          <div class="form-grid">
            <label class="field">
              <span class="field-label">Минимум сообщений в группе</span>
              <input v-model.number="form.min_support" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Минимум сегментов в группе</span>
              <input v-model.number="form.min_cluster_segments" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Максимум чужих совпадений</span>
              <input v-model.number="form.max_foreign_matches" class="input" type="number" min="0" />
            </label>
            <label class="field">
              <span class="field-label">Минимальная длина текста</span>
              <input v-model.number="form.min_text_length" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Максимум переменных %w в группе</span>
              <input v-model.number="form.max_w_words" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Максимум переменных %d в группе</span>
              <input v-model.number="form.max_d_words" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Слотов в слиянии литералов</span>
              <input v-model.number="form.max_word_slots_per_merge" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Максимум вариантов литерала</span>
              <input v-model.number="form.max_literal_cardinality" class="input" type="number" min="1" />
            </label>
            <label class="field">
              <span class="field-label">Глубина хвостовых вариантов</span>
              <input v-model.number="form.max_tail_depth" class="input" type="number" min="1" />
            </label>
          </div>
        </section>

        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Нормализация текста</div>
              <div class="card-caption">общая политика матчинга и группировки</div>
            </div>
          </div>
          <div class="form-grid">
            <label class="field">
              <span class="field-label">Пунктуация</span>
              <select v-model="form.punctuation_policy" class="select">
                <option v-for="option in punctuationOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <div class="field">
              <span class="field-label">Дополнительно</span>
              <label class="checkbox"><input v-model="form.fold_yo" type="checkbox" />Свёртка ё → е</label>
              <label class="checkbox"><input v-model="form.fold_homoglyphs" type="checkbox" />Свёртка омоглифов</label>
              <label class="checkbox"><input v-model="form.sender_case_sensitive" type="checkbox" />Учитывать регистр отправителя</label>
              <label class="checkbox"><input v-model="form.delivered_only" type="checkbox" />Только доставленные сообщения</label>
            </div>
          </div>
        </section>
      </div>

      <div class="row">
        <button class="btn btn-primary" type="button" :disabled="isBusy" @click="save">Сохранить настройки</button>
        <span v-if="saved" class="badge badge-positive">Сохранено</span>
        <span class="field-hint">Изменения сбрасывают кэш анализа: следующий расчёт выполнится заново.</span>
      </div>
    </template>

    <template v-else-if="tab === 'appearance'">
      <div class="row">
        <p class="muted small" style="margin: 0; flex: 1">
          Тема применяется сразу и сохраняется в settings.toml. Каждая тема задаёт палитру,
          шрифты, радиусы и отступы.
        </p>
        <button class="btn" type="button" @click="resetToSystemTheme">Сбросить к системной теме</button>
      </div>
      <div class="theme-grid">
        <button
          v-for="theme in state.themes"
          :key="theme.id"
          class="theme-card"
          :class="{ selected: state.settings?.theme === theme.id }"
          type="button"
          @click="chooseTheme(theme)"
        >
          <div class="theme-preview" :style="{ background: theme.palette.window, borderColor: theme.palette.border }">
            <div class="preview-sidebar" :style="{ background: theme.palette.surface, borderColor: theme.palette.border }">
              <span :style="{ background: theme.palette.accent }"></span>
              <i :style="{ background: theme.palette.text_muted }"></i>
              <i :style="{ background: theme.palette.text_muted }"></i>
            </div>
            <div class="preview-main">
              <div class="preview-bar" :style="{ background: theme.palette.header }"></div>
              <div class="preview-cards">
                <div :style="{ background: theme.palette.surface, borderColor: theme.palette.border }">
                  <b :style="{ background: theme.palette.text }"></b>
                  <em :style="{ background: theme.palette.positive }"></em>
                </div>
                <div :style="{ background: theme.palette.surface, borderColor: theme.palette.border }">
                  <b :style="{ background: theme.palette.text }"></b>
                  <em :style="{ background: theme.palette.negative }"></em>
                </div>
              </div>
              <div class="preview-chart" :style="{ background: theme.palette.surface_alt, borderColor: theme.palette.border }">
                <span :style="{ height: '45%', background: theme.palette.accent }"></span>
                <span :style="{ height: '70%', background: theme.palette.accent_secondary }"></span>
                <span :style="{ height: '35%', background: theme.palette.accent }"></span>
                <span :style="{ height: '58%', background: theme.palette.positive }"></span>
              </div>
            </div>
          </div>
          <div class="theme-meta">
            <div class="theme-name">{{ theme.name }}</div>
            <div class="theme-description">{{ theme.description }}</div>
          </div>
          <span v-if="state.settings?.theme === theme.id" class="badge badge-positive">Выбрана</span>
        </button>
      </div>
    </template>

    <template v-else>
      <div class="settings-grid">
        <section class="card">
          <div class="card-header"><div class="card-title">Каталог данных</div></div>
          <div class="details-grid">
            <span>Каталог данных</span><strong class="mono">{{ state.settings?.data_dir }}</strong>
            <span>База SQLite</span><strong class="mono">{{ state.settings?.database_path }}</strong>
            <span>Стоимость шаблона</span><strong>{{ money(state.settings?.template_fee ?? '0') }}</strong>
            <span>Тема</span><strong>{{ state.settings?.theme }}</strong>
          </div>
          <p class="field-hint" style="margin-top: 12px">
            Данные хранятся локально в профиле пользователя. Приложение не отправляет
            выгрузки во внешние сервисы и не содержит телеметрии.
          </p>
        </section>
        <section class="card">
          <div class="card-header"><div class="card-title">О программе</div></div>
          <p class="small">
            <strong>MTS Templates Optimus</strong> — анализ SMS-шаблонов и поиск кандидатов
            по выгрузкам МТС-Маркетолога.
          </p>
          <ul class="small muted" style="line-height: 1.6; padding-left: 18px">
            <li>Веб-версия: FastAPI + Vue 3, тот же домен и use cases, что у десктопа.</li>
            <li>Деньги считаются в Decimal и отдаются строками; проценты — долями.</li>
            <li>Сопоставление шаблонов — только по грамматике МТС, без fuzzy и ML.</li>
            <li>Кандидаты регистрируются только после подтверждения человеком.</li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tabs {
  display: inline-flex;
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface);
}

.tabs .btn {
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--text-muted);
}

.tabs .btn.active {
  background: var(--selection);
  color: var(--text);
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: calc(var(--space) * 2);
  align-items: stretch;
}

.settings-grid > section:last-child:nth-child(odd) {
  grid-column: 1 / -1;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: calc(var(--space) * 1.5);
}

.thresholds {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}

.details-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 16px;
  font-size: 12px;
  align-items: baseline;
}

.details-grid span {
  color: var(--text-muted);
}

.theme-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: calc(var(--space) * 1.75);
}

.theme-card {
  text-align: left;
  background: var(--surface);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--text);
  transition:
    transform 0.12s ease,
    border-color 0.12s ease;
  position: relative;
}

.theme-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
}

.theme-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent);
}

.theme-preview {
  height: 108px;
  border: 1px solid;
  border-radius: 6px;
  display: flex;
  overflow: hidden;
}

.preview-sidebar {
  width: 26%;
  border-right: 1px solid;
  padding: 8px 6px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.preview-sidebar span {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  margin-bottom: 4px;
}

.preview-sidebar i {
  height: 4px;
  border-radius: 2px;
  opacity: 0.55;
}

.preview-main {
  flex: 1;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.preview-bar {
  height: 9px;
  border-radius: 3px;
  opacity: 0.9;
}

.preview-cards {
  display: flex;
  gap: 5px;
}

.preview-cards div {
  flex: 1;
  height: 27px;
  border: 1px solid;
  border-radius: 4px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview-cards b {
  display: block;
  height: 3px;
  width: 65%;
  border-radius: 2px;
  opacity: 0.75;
}

.preview-cards em {
  display: block;
  height: 5px;
  width: 40%;
  border-radius: 2px;
}

.preview-chart {
  flex: 1;
  border: 1px solid;
  border-radius: 4px;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  padding: 4px;
}

.preview-chart span {
  flex: 1;
  border-radius: 2px 2px 0 0;
}

.theme-meta {
  min-height: 52px;
}

.theme-name {
  font-weight: 700;
  font-size: 13px;
}

.theme-description {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-top: 3px;
}

@media (max-width: 1400px) {
  .theme-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1180px) {
  .settings-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .theme-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .theme-grid {
    grid-template-columns: 1fr;
  }

  .thresholds {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
