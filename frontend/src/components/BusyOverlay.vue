<script setup lang="ts">
withDefaults(defineProps<{ text?: string }>(), { text: 'Выполняется операция…' })
</script>

<template>
  <div class="busy-overlay" role="status" aria-live="polite">
    <div class="spinner"></div>
    <div class="busy-text">{{ text }}</div>
  </div>
</template>

<style scoped>
.busy-text {
  font-weight: 600;
  color: var(--text);
  background: var(--surface);
  border: var(--border-width) solid var(--border);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 12px;
}
</style>
