import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import TemplatesView from './views/TemplatesView.vue'
import CandidatesView from './views/CandidatesView.vue'
import ImportView from './views/ImportView.vue'
import ExportView from './views/ExportView.vue'
import SettingsView from './views/SettingsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView, meta: { title: 'Дашборд' } },
    { path: '/templates', name: 'templates', component: TemplatesView, meta: { title: 'Шаблоны' } },
    {
      path: '/candidates',
      name: 'candidates',
      component: CandidatesView,
      meta: { title: 'Кандидаты' },
    },
    { path: '/import', name: 'import', component: ImportView, meta: { title: 'Импорт' } },
    { path: '/export', name: 'export', component: ExportView, meta: { title: 'Экспорт' } },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: 'Настройки' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? 'MTS Templates'
  document.title = `${title} — MTS Templates Optimus`
})
