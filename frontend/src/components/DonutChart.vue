<script setup lang="ts">
import { computed } from 'vue'
import { integer, share } from '../format'

interface Slice {
  name: string
  value: number
  color: string
}

const props = withDefaults(
  defineProps<{
    slices: Slice[]
    centerLabel?: string
    height?: number
  }>(),
  { centerLabel: '', height: 190 },
)

const SIZE = 180
const RADIUS = 76
const INNER = 48
const CENTER = SIZE / 2

const total = computed(() => props.slices.reduce((sum, slice) => sum + slice.value, 0))

function polar(radius: number, angle: number): [number, number] {
  const radians = ((angle - 90) * Math.PI) / 180
  return [CENTER + radius * Math.cos(radians), CENTER + radius * Math.sin(radians)]
}

const arcs = computed(() => {
  if (total.value <= 0) return []
  let angle = 0
  const result: { name: string; color: string; d: string; value: number; ratio: number }[] = []
  for (const slice of props.slices) {
    const ratio = slice.value / total.value
    if (ratio <= 0) continue
    const start = angle
    const end = angle + ratio * 360
    angle = end
    if (ratio >= 0.9999) {
      result.push({
        name: slice.name,
        color: slice.color,
        value: slice.value,
        ratio,
        d: `M ${CENTER - RADIUS} ${CENTER} A ${RADIUS} ${RADIUS} 0 1 1 ${CENTER + RADIUS} ${CENTER} A ${RADIUS} ${RADIUS} 0 1 1 ${CENTER - RADIUS} ${CENTER} Z
            M ${CENTER - INNER} ${CENTER} A ${INNER} ${INNER} 0 1 0 ${CENTER + INNER} ${CENTER} A ${INNER} ${INNER} 0 1 0 ${CENTER - INNER} ${CENTER} Z`,
      })
      continue
    }
    const [x1, y1] = polar(RADIUS, start)
    const [x2, y2] = polar(RADIUS, end)
    const [x3, y3] = polar(INNER, end)
    const [x4, y4] = polar(INNER, start)
    const large = end - start > 180 ? 1 : 0
    result.push({
      name: slice.name,
      color: slice.color,
      value: slice.value,
      ratio,
      d: `M ${x1} ${y1} A ${RADIUS} ${RADIUS} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${INNER} ${INNER} 0 ${large} 0 ${x4} ${y4} Z`,
    })
  }
  return result
})

const visibleSlices = computed(() => props.slices.filter((slice) => slice.value > 0))
</script>

<template>
  <div class="donut">
    <div v-if="!total" class="empty">Нет данных</div>
    <template v-else>
      <svg :viewBox="`0 0 ${SIZE} ${SIZE}`" :style="{ height: `${height}px` }" role="img" aria-label="Круговая диаграмма">
        <g v-for="arc in arcs" :key="arc.name">
          <path :d="arc.d" :fill="arc.color" stroke="var(--surface)" stroke-width="1.5">
            <title>{{ arc.name }}: {{ integer(arc.value) }} ({{ share(arc.ratio) }})</title>
          </path>
        </g>
        <text
          v-if="centerLabel"
          :x="CENTER"
          :y="CENTER + 4"
          text-anchor="middle"
          font-size="12"
          font-weight="700"
          fill="var(--text)"
        >
          {{ centerLabel }}
        </text>
      </svg>
      <div class="donut-legend">
        <div v-for="slice in visibleSlices" :key="slice.name" class="donut-legend-item">
          <i :style="{ background: slice.color }"></i>
          <span class="donut-name">{{ slice.name }}</span>
          <span class="donut-share">{{ share(slice.value / total) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.donut {
  display: flex;
  align-items: center;
  gap: calc(var(--space) * 2);
  flex-wrap: wrap;
  min-width: 0;
}

svg {
  flex: 0 0 auto;
  width: auto;
  max-width: 46%;
  min-width: 130px;
}

.donut-legend {
  flex: 1;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.donut-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}

.donut-legend-item i {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.donut-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.donut-share {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
