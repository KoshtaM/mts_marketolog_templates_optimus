<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { clearError, init, state } from './store'

onMounted(() => {
  void init()
})

const navigation = [
  { to: '/', label: 'Дашборд', icon: '▦' },
  { to: '/templates', label: 'Шаблоны', icon: '✉' },
  { to: '/candidates', label: 'Кандидаты', icon: '✦' },
  { to: '/import', label: 'Импорт', icon: '⇣' },
  { to: '/export', label: 'Экспорт', icon: '⇡' },
  { to: '/settings', label: 'Настройки', icon: '⚙' },
]
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">MTS</div>
        <div>
          <div class="brand-title">Templates<br />Optimus</div>
          <div class="brand-subtitle">веб-версия</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-link">
          <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div v-if="state.settings">
          <div class="tiny muted">Данные</div>
          <div>{{ state.settings.data_dir }}</div>
        </div>
        <div>FastAPI · Vue 3</div>
      </div>
    </aside>

    <main class="main">
      <div v-if="!state.ready" class="empty">
        <div class="spinner" style="margin: 0 auto 12px"></div>
        Подключение к серверу…
      </div>
      <RouterView v-else />
    </main>

    <div v-if="state.error" class="toast" role="alert">
      <div style="flex: 1">
        <strong>Не удалось выполнить операцию</strong>
        <div class="small" style="margin-top: 4px">{{ state.error }}</div>
      </div>
      <button class="btn btn-ghost" type="button" @click="clearError">✕</button>
    </div>
  </div>
</template>

<style scoped>
.nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1280px) {
  .nav-label {
    display: none;
  }
}
</style>
