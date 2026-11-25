<script setup lang="ts">
import { computed } from 'vue'
import { integer } from '../format'

interface Part {
  name: string
  value: number
  color: string
}

interface StackItem {
  label: string
  total: number
  parts: Part[]
}

const props = withDefaults(
  defineProps<{
    items: StackItem[]
    height?: number
    caption?: string
    unit?: string
  }>(),
  { height: 230, caption: '', unit: 'сегментов' },
)

const WIDTH = 860

const maxTotal = computed(() => Math.max(1, ...props.items.map((item) => item.total)))

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
  const step = niceStep(maxTotal.value / 4)
  const top = Math.ceil(maxTotal.value / step) * step
  const ticks: number[] = []
  for (let value = 0; value <= top + step / 2; value += step) {
    ticks.push(Math.round(value * 100) / 100)
  }
  return { top: Math.max(top, step), ticks }
})

const margin = { left: 52, right: 10, top: 10, bottom: 26 }
const plotWidth = computed(() => WIDTH - margin.left - margin.right)
const plotHeight = computed(() => props.height - margin.top - margin.bottom)

function x(index: number): number {
  const slot = plotWidth.value / Math.max(1, props.items.length)
  return margin.left + slot * index
}

function barWidth(): number {
  const slot = plotWidth.value / Math.max(1, props.items.length)
  return Math.max(2, slot * 0.78)
}

function y(value: number): number {
  return margin.top + plotHeight.value * (1 - value / scale.value.top)
}

function barHeight(value: number): number {
  return (plotHeight.value * value) / scale.value.top
}

const bars = computed(() =>
  props.items.map((item, index) => {
    let cursor = 0
    const segments = item.parts
      .filter((part) => part.value > 0)
      .map((part) => {
        const height = barHeight(part.value)
        const rect = {
          name: part.name,
          value: part.value,
          color: part.color,
          x: x(index) + (plotWidth.value / Math.max(1, props.items.length) - barWidth()) / 2,
          y: y(cursor + part.value),
          height,
        }
        cursor += part.value
        return rect
      })
    return { ...item, x: x(index), segments }
  }),
)

const labelStep = computed(() => Math.max(1, Math.ceil(props.items.length / 16)))

const legend = computed(() => {
  const totals = new Map<string, { name: string; color: string; value: number }>()
  for (const item of props.items) {
    for (const part of item.parts) {
      const current = totals.get(part.name)
      if (current) current.value += part.value
      else totals.set(part.name, { name: part.name, color: part.color, value: part.value })
    }
  }
  return [...totals.values()].filter((item) => item.value > 0).sort((a, b) => b.value - a.value)
})
</script>

<template>
  <div class="chart">
    <div v-if="caption" class="card-caption" style="margin-bottom: 8px">{{ caption }}</div>
    <div v-if="!items.length" class="empty">Нет данных за период</div>
    <svg
      v-else
      :viewBox="`0 0 ${WIDTH} ${height}`"
      :style="{ height: `${height}px` }"
      role="img"
      aria-label="Столбчатая диаграмма по дням"
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
          opacity="0.75"
        />
        <text
          v-for="tick in scale.ticks"
          :key="`label-${tick}`"
          :x="margin.left - 8"
          :y="y(tick) + 3.5"
          text-anchor="end"
          font-size="10"
          fill="var(--text-muted)"
        >
          {{ integer(tick) }}
        </text>
      </g>
      <g v-for="(bar, index) in bars" :key="bar.label">
        <rect
          v-for="segment in bar.segments"
          :key="`${bar.label}-${segment.name}`"
          :x="segment.x"
          :y="segment.y"
          :width="barWidth()"
          :height="segment.height"
          :fill="segment.color"
          rx="1.5"
        >
          <title>{{ bar.label }} · {{ segment.name }}: {{ integer(segment.value) }}</title>
        </rect>
        <text
          v-if="index % labelStep === 0"
          :x="bar.x + plotWidth / Math.max(1, items.length) / 2"
          :y="height - 8"
          text-anchor="middle"
          font-size="9.5"
          fill="var(--text-muted)"
        >
          {{ bar.label }}
        </text>
      </g>
    </svg>
    <div v-if="legend.length" class="legend">
      <span v-for="item in legend" :key="item.name" class="legend-item">
        <i :style="{ background: item.color }"></i>{{ item.name }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.chart {
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
  gap: 6px 14px;
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
