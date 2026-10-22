import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layout/AppLayout.vue'),
    redirect: '/tenants',
    children: [
      { path: 'tenants', name: 'tenants', component: () => import('@/views/Tenants.vue'), meta: { title: '租户管理' } },
      { path: 'tenants/:id/resources', name: 'tenantResources', component: () => import('@/views/TenantResources.vue'), meta: { title: '租户资源管理' } },
      { path: 'sessions', name: 'sessions', component: () => import('@/views/Sessions.vue'), meta: { title: '对话记录' } },
      // 旧资源池（TTS/ASR/LLM Factories）页面已下线（2026-10-22）：
      // 资源管理统一走「基础插件 + 个性插件」，对话模板保留查看/绑定
      { path: 'chatTemplate', name: 'chatTemplate', component: () => import('@/views/ResourceList.vue'), props: { resType: 'CHATTEMPLATE' }, meta: { title: '对话模板' } },
      { path: 'basePlugins', name: 'basePlugins', component: () => import('@/views/BasePlugins.vue'), meta: { title: '基础插件' } },
      { path: 'customPlugins', name: 'customPlugins', component: () => import('@/views/CustomPlugins.vue'), meta: { title: '个性插件' } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/tenants' }
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return { name: 'login' }
  if (to.name === 'login' && auth.token) return { name: 'tenants' }
  return true
})

export default router
