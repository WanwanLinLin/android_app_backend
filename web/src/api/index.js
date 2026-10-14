import { http } from './http'

export * from './http'

// ===================== 登录（User 表管理员）=====================
export const login = (payload) => http.post('/v1/user/login', payload)
export const logout = () => http.post('/v1/user/logout')
export const userList = () => http.get('/v1/user/list')

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

// ===================== 资源 CRUD（TTS / ASR / LLM / CHATTEMPLATE）=====================
// 注意：list/add 为开放接口；get 详情中仅 TTS 受对称加密保护（getNeedsAccesskey: true）
export const RES_META = {
  TTS: { list: '/v1/tts/list', add: '/v1/tts/add', get: '/v1/tts/get/{id}', update: '/v1/tts/update/{id}', delete: '/v1/tts/delete/{id}', getNeedsAccesskey: true },
  ASR: { list: '/v1/asr/list', add: '/v1/asr/add', get: '/v1/asr/get/{id}', update: '/v1/asr/update/{id}', delete: '/v1/asr/delete/{id}', getNeedsAccesskey: false },
  LLM: { list: '/v1/agent/list', add: '/v1/agent/add', get: '/v1/agent/get/{id}', update: '/v1/agent/update/{id}', delete: '/v1/agent/delete/{id}', getNeedsAccesskey: false },
  CHATTEMPLATE: { list: '/v1/chatTemplate/list', add: '/v1/chatTemplate/add', get: '/v1/chatTemplate/get/{id}', update: '/v1/chatTemplate/update/{id}', delete: '/v1/chatTemplate/delete/{id}', getNeedsAccesskey: false }
}

export const resourceList = (t) => http.post(RES_META[t].list)

export const resourceAdd = (t, payload) => http.post(RES_META[t].add, payload)

export const resourceGet = (t, id) =>
  http.get(RES_META[t].get.replace('{id}', id), { accesskey: RES_META[t].getNeedsAccesskey })

export const resourceUpdate = (t, id, payload) =>
  http.post(RES_META[t].update.replace('{id}', id), payload)

export const resourceDelete = (t, id) =>
  http.post(RES_META[t].delete.replace('{id}', id))
