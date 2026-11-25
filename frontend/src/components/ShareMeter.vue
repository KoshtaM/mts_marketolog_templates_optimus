<script setup lang="ts">
import { computed } from 'vue'
import { share } from '../format'

const props = withDefaults(
  defineProps<{
    value: number
    color?: string
    label?: string
    showValue?: boolean
  }>(),
  { color: 'var(--accent)', label: '', showValue: true },
)

const width = computed(() => `${Math.max(0, Math.min(1, props.value)) * 100}%`)
</script>

<template>
  <div class="share-meter">
    <div class="share-track">
      <div class="share-fill" :style="{ width, background: color }"></div>
    </div>
    <span v-if="showValue" class="share-value">{{ label || share(value) }}</span>
  </div>
</template>

<style scoped>
.share-meter {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 90px;
}

.share-track {
  flex: 1;
  height: 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--border) 70%, transparent);
  overflow: hidden;
  min-width: 46px;
}

.share-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.25s ease;
}

.share-value {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 42px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
