<script setup lang="ts">
import { computed } from 'vue'
import { dayLabel, integer } from '../format'
import { MATCHED_COLOR, TEMPLATED_COLOR } from '../theme'

interface DayValue {
  day: string
  segments: number
}

const props = withDefaults(
  defineProps<{
    base: DayValue[]
    matched: DayValue[]
    height?: number
    matchedLabel?: string
    seriesLabel?: string
    caption?: string
  }>(),
  {
    height: 190,
    matchedLabel: 'Соответствуют шаблону',
    seriesLabel: 'Остальной трафик',
    caption: '',
  },
)

const WIDTH = 760

const matchedMap = computed(
  () => new Map(props.matched.map((item) => [item.day, item.segments])),
)

const maxTotal = computed(() =>
  Math.max(
    1,
    ...props.base.map((item) => item.segments),
    ...props.matched.map((item) => item.segments),
  ),
)

function niceStep(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const normalized = value / power
  if (normalized <= 1) return power
  if (normalized <= 2) return 2 * power
  if (normalized <= 2.5) return 2.5 * power
  if (normalized <= 5) return 5 * power
  return 10 * power
}

const scale = computed(() => {
  const step = niceStep(maxTotal.value / 3)
  const top = Math.ceil(maxTotal.value / step) * step
  const ticks: number[] = []
  for (let value = 0; value <= top + step / 2; value += step) {
    ticks.push(Math.round(value * 100) / 100)
  }
  return { top: Math.max(top, step), ticks }
})

const margin = { left: 46, right: 8, top: 8, bottom: 24 }
const plotWidth = computed(() => WIDTH - margin.left - margin.right)
const plotHeight = computed(() => props.height - margin.top - margin.bottom)

function y(value: number): number {
  return margin.top + plotHeight.value * (1 - value / scale.value.top)
}

function heightOf(value: number): number {
  return (plotHeight.value * value) / scale.value.top
}

const bars = computed(() => {
  const slot = plotWidth.value / Math.max(1, props.base.length)
  const width = Math.max(2, slot * 0.78)
  return props.base.map((item, index) => {
    const matched = matchedMap.value.get(item.day) ?? 0
    const x = margin.left + slot * index + (slot - width) / 2
    return {
      day: item.day,
      total: item.segments,
      matched,
      x,
      width,
      baseY: y(item.segments),
      baseHeight: heightOf(item.segments),
      matchedY: y(matched),
      matchedHeight: matched > 0 ? Math.max(2, heightOf(matched)) : 0,
    }
  })
})

const labelStep = computed(() => Math.max(1, Math.ceil(bars.value.length / 12)))

const matchedTotal = computed(() => props.matched.reduce((sum, item) => sum + item.segments, 0))
const baseTotal = computed(() => props.base.reduce((sum, item) => sum + item.segments, 0))

const autoCaption = computed(() => {
  if (props.caption) return props.caption
  return `${props.matchedLabel.toLowerCase()}: ${integer(matchedTotal.value)} из ${integer(baseTotal.value)} сегментов`
})
</script>

<template>
  <div class="segment-chart">
    <div class="card-caption" style="margin-bottom: 6px">{{ autoCaption }}</div>
    <div v-if="!base.length" class="empty">Нет данных за период</div>
    <svg
      v-else
      :viewBox="`0 0 ${WIDTH} ${height}`"
      :style="{ height: `${height}px` }"
      role="img"
      aria-label="Сегменты по дням"
    >
      <g>
        <line
          v-for="tick in scale.ticks"
          :key="tick"
          :x1="margin.left"
          :x2="WIDTH - margin.right"
          :y1="y(tick)"
          :y2="y(tick)"
          stroke="var(--border)"
          stroke-width="0.7"
          opacity="0.7"
        />
        <text
          v-for="tick in scale.ticks"
          :key="`label-${tick}`"
          :x="margin.left - 7"
          :y="y(tick) + 3.5"
          text-anchor="end"
          font-size="9.5"
          fill="var(--text-muted)"
        >
          {{ integer(tick) }}
        </text>
      </g>
      <g v-for="(bar, index) in bars" :key="bar.day">
        <rect
          :x="bar.x"
          :y="bar.baseY"
          :width="bar.width"
          :height="bar.baseHeight"
          :fill="TEMPLATED_COLOR"
          rx="1.5"
        >
          <title>{{ dayLabel(bar.day) }} · {{ seriesLabel }}: {{ integer(bar.total) }}</title>
        </rect>
        <rect
          v-if="bar.matchedHeight > 0"
          :x="bar.x"
          :y="bar.matchedY"
          :width="bar.width"
          :height="bar.matchedHeight"
          :fill="MATCHED_COLOR"
          rx="1.5"
        >
          <title>{{ dayLabel(bar.day) }} · {{ matchedLabel }}: {{ integer(bar.matched) }}</title>
        </rect>
        <text
          v-if="index % labelStep === 0"
          :x="bar.x + bar.width / 2"
          :y="height - 7"
          text-anchor="middle"
          font-size="9.5"
          fill="var(--text-muted)"
        >
          {{ dayLabel(bar.day) }}
        </text>
      </g>
    </svg>
    <div class="legend">
      <span class="legend-item"><i :style="{ background: MATCHED_COLOR }"></i>{{ matchedLabel }}</span>
      <span class="legend-item"><i :style="{ background: TEMPLATED_COLOR }"></i>{{ seriesLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.segment-chart {
  min-width: 0;
}

svg {
  width: 100%;
  display: block;
  overflow: visible;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 8px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.legend-item i {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}
</style>
