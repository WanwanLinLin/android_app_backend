import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, me as apiMe } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('dh_token') || '')
  const username = ref(localStorage.getItem('dh_username') || '')
  // role 来自后端 User.role（admin / user）。仅用于前端隐藏无权限入口，
  // 真正的权限判定以后端 require_admin 为准；缺失时按最小权限（非管理员）处理。
  const role = ref(localStorage.getItem('dh_role') || '')

  const isAdmin = computed(() => (role.value || '').toLowerCase() === 'admin')

  function setAuth(tok, name, roleVal) {
    token.value = tok
    username.value = name
    role.value = roleVal || ''
    localStorage.setItem('dh_token', tok)
    localStorage.setItem('dh_username', name)
    localStorage.setItem('dh_role', role.value)
  }

  function clear() {
    token.value = ''
    username.value = ''
    role.value = ''
    localStorage.removeItem('dh_token')
    localStorage.removeItem('dh_username')
    localStorage.removeItem('dh_role')
  }

  async function login(payload) {
    const data = await apiLogin(payload)
    setAuth(data.access_token, payload.username, data.role)
    return data
  }

  // 刷新页面后 token 仍在本地，但 role 可能是旧值（管理员改过角色）。
  // 进后台时拉一次 /v1/user/me 对齐；失败（如 token 失效）由拦截器处理。
  async function refreshMe() {
    if (!token.value) return
    try {
      const data = await apiMe()
      if (data) setAuth(token.value, data.username || username.value, data.role)
    } catch (e) { /* 网络异常保留本地 role，不阻塞页面 */ }
  }

  return { token, username, role, isAdmin, setAuth, clear, login, refreshMe }
})
