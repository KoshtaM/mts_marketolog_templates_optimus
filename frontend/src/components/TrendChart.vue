<script setup lang="ts">
import { computed } from 'vue'
import type { TemplateTrendPoint } from '../types'

export type TrendMetric = 'segments' | 'trigger_rate' | 'net_benefit'

const props = withDefaults(
  defineProps<{
    points: TemplateTrendPoint[]
    metric?: TrendMetric
  }>(),
  { metric: 'trigger_rate' },
)

const W = 320
const H = 110
const PAD_X = 14
const TOP = 14
const BOTTOM = 88

const values = computed<number[]>(() =>
  props.points.map((point) => {
    if (props.metric === 'segments') return point.segments
    if (props.metric === 'trigger_rate') return Number(point.trigger_rate)
    return Number(point.net_benefit)
  }),
)

const maxAbs = computed<number>(() => values.value.reduce((max, value) => Math.max(max, Math.abs(value)), 0))

function y(value: number): number {
  if (maxAbs.value <= 0) return BOTTOM - 16
  const range = maxAbs.value * 2
  return BOTTOM - ((value + maxAbs.value) / range) * (BOTTOM - TOP)
}

function x(index: number): number {
  const count = props.points.length
  if (count <= 1) return W / 2
  const step = (W - PAD_X * 2) / (count - 1)
  return PAD_X + index * step
}

const path = computed<string>(() =>
  props.points.map((_, index) => `${x(index)},${y(values.value[index])}`).join(' '),
)

const dots = computed(() =>
  props.points.map((point, index) => ({ batch_id: point.batch_id, cx: x(index), cy: y(values.value[index]) })),
)

const stroke = computed<string>(() => {
  if (props.metric === 'segments') return '#ff8c00'
  if (props.metric === 'trigger_rate') return '#0d9488'
  const last = values.value[values.value.length - 1] ?? 0
  return last >= 0 ? '#16a34a' : '#dc2626'
})
</script>

<template>
  <div v-if="points.length">
    <svg viewBox="0 0 320 110" class="trend-chart" preserveAspectRatio="none" role="img">
      <polyline
        :points="path"
        fill="none"
        :stroke="stroke"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <circle v-for="dot in dots" :key="dot.batch_id" :cx="dot.cx" :cy="dot.cy" r="2.5" :fill="stroke" />
    </svg>
    <div v-if="points.length === 1" class="trend-single">Нет предыдущих загрузок для тренда</div>
  </div>
  <div v-else class="empty">Тренд по загрузкам пока не построен</div>
</template>

<style scoped>
.trend-chart {
  width: 100%;
  height: 110px;
}

.trend-single {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
