<script setup lang="ts">
import { computed } from 'vue'
import type { Bar } from '../distribution'
import { integer, share } from '../format'

const props = withDefaults(
  defineProps<{
    bars: Bar[]
    height?: number
    color?: string
    caption?: string
  }>(),
  { height: 150, color: 'var(--accent)', caption: '' },
)

const maxCount = computed(() => Math.max(1, ...props.bars.map((bar) => bar.count)))

function barHeight(count: number): string {
  if (count <= 0) return '0%'
  return `${Math.max(2, (count / maxCount.value) * 100)}%`
}
</script>

<template>
  <div class="distribution">
    <div v-if="caption" class="card-caption" style="margin-bottom: 8px">{{ caption }}</div>
    <div v-if="!bars.length" class="empty">Нет данных</div>
    <div v-else class="bars" :style="{ height: `${height}px` }">
      <div v-for="bar in bars" :key="bar.label" class="column" :title="`${bar.label}: ${integer(bar.count)} · ${share(bar.share)}`">
        <div class="count">{{ integer(bar.count) }}</div>
        <div class="track">
          <div
            class="fill"
            :class="{ grouped: bar.grouped }"
            :style="{ height: barHeight(bar.count), background: bar.grouped ? 'color-mix(in srgb, ' + color + ' 55%, var(--text-muted))' : color }"
          ></div>
        </div>
        <div class="label">{{ bar.label }}</div>
        <div class="share">{{ share(bar.share, 0) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.distribution {
  min-width: 0;
}

.bars {
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding-top: 4px;
}

.column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 3px;
}

.count {
  font-size: 9.5px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  height: 13px;
  overflow: hidden;
  white-space: nowrap;
}

.track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  border-bottom: 1px solid var(--border);
  min-height: 0;
}

.fill {
  width: 100%;
  border-radius: 3px 3px 0 0;
  transition: height 0.25s ease;
  opacity: 0.92;
}

.label {
  font-size: 9.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.share {
  font-size: 8.5px;
  color: var(--text-muted);
  opacity: 0.8;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
