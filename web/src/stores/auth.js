import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, me as apiMe } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('dh_token') || '')
  const username = ref(localStorage.getItem('dh_username') || '')
  // role 来自后端 User.role（admin / user）。仅用于前端隐藏无权限入口，
  // 真正的权限判定以后端 require_admin 为准；缺失时按最小权限（非管理员）处理。
  const role = ref(localStorage.getItem('dh_role') || '')
  // User.id：个性插件「是否我的」判定用（后端仍独立强校验）
  const id = ref(Number(localStorage.getItem('dh_uid') || 0) || null)

  const isAdmin = computed(() => (role.value || '').toLowerCase() === 'admin')

  function setAuth(tok, name, roleVal, uid) {
    token.value = tok
    username.value = name
    role.value = roleVal || ''
    if (uid !== undefined && uid !== null) id.value = uid
    localStorage.setItem('dh_token', tok)
    localStorage.setItem('dh_username', name)
    localStorage.setItem('dh_role', role.value)
    if (id.value) localStorage.setItem('dh_uid', String(id.value))
  }

  function clear() {
    token.value = ''
    username.value = ''
    role.value = ''
    id.value = null
    localStorage.removeItem('dh_token')
    localStorage.removeItem('dh_username')
    localStorage.removeItem('dh_role')
    localStorage.removeItem('dh_uid')
  }

  async function login(payload) {
    const data = await apiLogin(payload)
    // 登录响应带 role/nickname；id 由随后的 refreshMe 补齐
    setAuth(data.access_token, payload.username, data.role, data.id)
    return data
  }

  // 刷新页面后 token 仍在本地，但 role 可能是旧值（管理员改过角色）。
  // 进后台时拉一次 /v1/user/me 对齐；失败（如 token 失效）由拦截器处理。
  async function refreshMe() {
    if (!token.value) return
    try {
      const data = await apiMe()
      if (data) setAuth(token.value, data.username || username.value, data.role, data.id)
    } catch (e) { /* 网络异常保留本地 role，不阻塞页面 */ }
  }

  return { token, username, role, id, isAdmin, setAuth, clear, login, refreshMe }
})
