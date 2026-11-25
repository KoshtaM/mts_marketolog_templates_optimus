<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    tone?: 'default' | 'positive' | 'negative' | 'warning'
    compact?: boolean
  }>(),
  { hint: '', tone: 'default', compact: false },
)
</script>

<template>
  <div class="kpi" :class="{ compact }">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value" :class="tone !== 'default' ? tone : ''">{{ value }}</div>
    <div v-if="hint" class="kpi-hint">
      <slot name="hint">{{ hint }}</slot>
    </div>
  </div>
</template>

<style scoped>
.kpi {
  background: var(--surface);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius);
  padding: calc(var(--space) * 1.75);
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  box-shadow: 0 1px 2px color-mix(in srgb, var(--shadow) 16%, transparent);
}

html[data-hard-shadow='true'] .kpi {
  box-shadow: 4px 4px 0 color-mix(in srgb, var(--text) 85%, transparent);
}

.kpi-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  font-weight: 700;
}

.kpi-value {
  font-family: var(--font-heading);
  font-size: 25px;
  line-height: 1.15;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-value.positive,
.kpi-value.negative,
.kpi-value.warning {
  border-radius: 10px;
  padding: 2px 8px;
  margin-left: -8px;
  margin-right: -8px;
  width: calc(100% + 16px);
}

.kpi-value.positive {
  background: color-mix(in srgb, var(--positive) 10%, var(--surface));
}

.kpi-value.negative {
  background: color-mix(in srgb, var(--negative) 10%, var(--surface));
}

.kpi-value.warning {
  background: color-mix(in srgb, var(--warning) 10%, var(--surface));
}

.kpi.compact .kpi-value {
  font-size: 21px;
}

.kpi-hint {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  min-height: 15px;
}
</style>
