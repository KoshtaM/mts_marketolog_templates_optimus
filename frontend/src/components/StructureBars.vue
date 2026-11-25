<script setup lang="ts">
import { computed } from 'vue'
import { share } from '../format'
import { ORDINARY_COLOR, TEMPLATED_COLOR } from '../theme'

const props = defineProps<{
  ordinarySegmentShare: number
  templatedSegmentShare: number
  ordinaryCostShare: number
  templatedCostShare: number
}>()

interface Row {
  label: string
  ordinary: number
  templated: number
}

const rows = computed<Row[]>(() => [
  {
    label: 'SMS-сегменты',
    ordinary: props.ordinarySegmentShare,
    templated: props.templatedSegmentShare,
  },
  { label: 'Расходы', ordinary: props.ordinaryCostShare, templated: props.templatedCostShare },
])
</script>

<template>
  <div class="structure">
    <div v-for="row in rows" :key="row.label" class="structure-row">
      <div class="structure-label">
        <span>{{ row.label }}</span>
        <span class="tiny muted">
          обычные {{ share(row.ordinary, 0) }} · шаблонированные {{ share(row.templated, 0) }}
        </span>
      </div>
      <div class="structure-track" role="img" :aria-label="row.label">
        <div
          class="structure-fill"
          :style="{ width: `${row.ordinary * 100}%`, background: ORDINARY_COLOR }"
          :title="`Обычные: ${share(row.ordinary)}`"
        ></div>
        <div
          class="structure-fill"
          :style="{ width: `${row.templated * 100}%`, background: TEMPLATED_COLOR }"
          :title="`Шаблонированные: ${share(row.templated)}`"
        ></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.structure {
  display: flex;
  flex-direction: column;
  gap: calc(var(--space) * 1.75);
}

.structure-label {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.structure-track {
  display: flex;
  height: 16px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface-alt);
}

.structure-fill {
  height: 100%;
  transition: width 0.25s ease;
}
</style>
