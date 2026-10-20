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
      { path: 'tts', name: 'tts', component: () => import('@/views/ResourceList.vue'), props: { resType: 'TTS' }, meta: { title: 'TTS 资源' } },
      { path: 'asr', name: 'asr', component: () => import('@/views/ResourceList.vue'), props: { resType: 'ASR' }, meta: { title: 'ASR 资源' } },
      { path: 'llm', name: 'llm', component: () => import('@/views/ResourceList.vue'), props: { resType: 'LLM' }, meta: { title: 'LLM 资源' } },
      { path: 'chatTemplate', name: 'chatTemplate', component: () => import('@/views/ResourceList.vue'), props: { resType: 'CHATTEMPLATE' }, meta: { title: '对话模板' } }
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
