import { http } from './http'

export * from './http'

// ===================== 登录（User 表管理员）=====================
export const login = (payload) => http.post('/v1/user/login', payload)
export const logout = () => http.post('/v1/user/logout')
export const userList = () => http.get('/v1/user/list')
export const me = () => http.get('/v1/user/me')

// ===================== 租户管理（需 JWT）=====================
export const tenantList = () => http.get('/v1/tenant/list')
export const tenantGet = (id) => http.get(`/v1/tenant/get/${id}`)
export const tenantAdd = (payload) => http.post('/v1/tenant/add', payload)
export const tenantUpdate = (id, payload) => http.post(`/v1/tenant/update/${id}`, payload)
export const tenantDelete = (id) => http.post(`/v1/tenant/delete/${id}`)

// 租户资源绑定
export const tenantBindSource = (id, payload) => http.post(`/v1/tenant/${id}/source/bind`, payload)
export const tenantUnbindSource = (id, payload) => http.post(`/v1/tenant/${id}/source/unbind`, payload)
export const tenantSourceList = (id) => http.get(`/v1/tenant/${id}/source/list`)
export const tenantSetDefault = (id, payload) => http.post(`/v1/tenant/${id}/source/setDefault`, payload)

// ===================== 对话记录（AgentSessionManagement，只读审计）=====================
// list: {tenant_id?, start?, end?, page, size} → {rows, total}；get 返回含 dialogue_history 全文
export const sessionList = (params) => http.get('/v1/session/list', { params })
export const sessionGet = (id) => http.get(`/v1/session/get/${id}`)

// ===================== 资源 CRUD（TTS / ASR / LLM / CHATTEMPLATE）=====================
// 全部接口均需 JWT（http 拦截器自动注入 Authorization）；
// TTS/figure 的 get 详情额外要求对称加密头（getNeedsAccesskey: true）
export const RES_META = {
  TTS: { list: '/v1/tts/list', add: '/v1/tts/add', get: '/v1/tts/get/{id}', update: '/v1/tts/update/{id}', delete: '/v1/tts/delete/{id}', offShelfPreview: '/v1/tts/offShelfPreview/{id}', offShelf: '/v1/tts/offShelf/{id}', onShelf: '/v1/tts/onShelf/{id}', getNeedsAccesskey: true },
  ASR: { list: '/v1/asr/list', add: '/v1/asr/add', get: '/v1/asr/get/{id}', update: '/v1/asr/update/{id}', delete: '/v1/asr/delete/{id}', offShelfPreview: '/v1/asr/offShelfPreview/{id}', offShelf: '/v1/asr/offShelf/{id}', onShelf: '/v1/asr/onShelf/{id}', getNeedsAccesskey: false },
  LLM: { list: '/v1/agent/list', add: '/v1/agent/add', get: '/v1/agent/get/{id}', update: '/v1/agent/update/{id}', delete: '/v1/agent/delete/{id}', offShelfPreview: '/v1/agent/offShelfPreview/{id}', offShelf: '/v1/agent/offShelf/{id}', onShelf: '/v1/agent/onShelf/{id}', getNeedsAccesskey: false },
  CHATTEMPLATE: { list: '/v1/chatTemplate/list', add: '/v1/chatTemplate/add', get: '/v1/chatTemplate/get/{id}', update: '/v1/chatTemplate/update/{id}', delete: '/v1/chatTemplate/delete/{id}', offShelfPreview: '/v1/chatTemplate/offShelfPreview/{id}', offShelf: '/v1/chatTemplate/offShelf/{id}', onShelf: '/v1/chatTemplate/onShelf/{id}', getNeedsAccesskey: false }
}

export const resourceList = (t) => http.post(RES_META[t].list)

export const resourceAdd = (t, payload) => http.post(RES_META[t].add, payload)

export const resourceGet = (t, id) =>
  http.get(RES_META[t].get.replace('{id}', id), { accesskey: RES_META[t].getNeedsAccesskey })

export const resourceUpdate = (t, id, payload) =>
  http.post(RES_META[t].update.replace('{id}', id), payload)

export const resourceDelete = (t, id) =>
  http.post(RES_META[t].delete.replace('{id}', id))

// 上下架：下架只关闭新增绑定/设默认入口，存量租户照常可用；删除才会影响存量
export const resourceOffShelfPreview = (t, id) =>
  http.get(RES_META[t].offShelfPreview.replace('{id}', id))

export const resourceOffShelf = (t, id) =>
  http.post(RES_META[t].offShelf.replace('{id}', id))

export const resourceOnShelf = (t, id) =>
  http.post(RES_META[t].onShelf.replace('{id}', id))
