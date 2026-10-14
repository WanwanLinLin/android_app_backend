import axios from 'axios'
import { ElMessage } from 'element-plus'
import { accesskeyHeaders } from './accesskey'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30000
})

// 请求拦截：自动注入 JWT；对 accesskey=true 的请求注入对称加密头（dk/token）
http.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) cfg.headers.Authorization = `Bearer ${auth.token}`
  if (cfg.accesskey) Object.assign(cfg.headers, accesskeyHeaders())
  return cfg
})

// 响应拦截：后端统一 {code,msg,data}，业务码非 200 时抛出；401 跳登录
http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body.code !== 'undefined' && body.code !== 200) {
      if (body.code === 401) {
        const auth = useAuthStore()
        auth.clear()
        if (router.currentRoute.value.name !== 'login') router.push({ name: 'login' })
      }
      return Promise.reject(new Error(body.msg || '请求失败'))
    }
    return body && typeof body.code !== 'undefined' ? body.data : body
  },
  (err) => {
    const msg = err.response ? `HTTP ${err.response.status}` : (err.message || '网络错误')
    return Promise.reject(new Error(msg))
  }
)

// 统一错误提示的调用包装
export async function call(promise, { silent = false } = {}) {
  try {
    return await promise
  } catch (e) {
    if (!silent) ElMessage.error(e.message)
    throw e
  }
}
