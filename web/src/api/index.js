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

// 资源连通性检测：{url, port?, timeout?} → {reachable, host, port, latency_ms, error}
export const connectCheck = (payload) => http.post('/v1/connectCheck', payload)

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

// ===================== 基础插件（utils/providers 代码插件登记，写操作仅管理员）=====================
export const basePluginList = () => http.post('/v1/basePlugin/list')
export const basePluginGet = (id) => http.get(`/v1/basePlugin/get/${id}`)
export const basePluginAdd = (payload) => http.post('/v1/basePlugin/add', payload)
export const basePluginUpdate = (id, payload) => http.post(`/v1/basePlugin/update/${id}`, payload)
export const basePluginDelete = (id) => http.post(`/v1/basePlugin/delete/${id}`)
export const basePluginOffShelfPreview = (id) => http.get(`/v1/basePlugin/offShelfPreview/${id}`)
export const basePluginOffShelf = (id) => http.post(`/v1/basePlugin/offShelf/${id}`)
export const basePluginOnShelf = (id) => http.post(`/v1/basePlugin/onShelf/${id}`)

// ===================== 个性插件（用户在基础插件上定义的私有配置）=====================
// category: TTS | ASR | LLM；普通用户见自己的+平台的，admin 见全部
export const customPluginList = (category) => http.get('/v1/customPlugin/list', { params: { category } })
export const customPluginGet = (id) => http.get(`/v1/customPlugin/get/${id}`)
export const customPluginAdd = (payload) => http.post('/v1/customPlugin/add', payload)
export const customPluginUpdate = (id, payload) => http.post(`/v1/customPlugin/update/${id}`, payload)
export const customPluginDelete = (id) => http.post(`/v1/customPlugin/delete/${id}`)

// ===================== LLM 自动化测试（插件测试模块）=====================
// 任务 CRUD 走通用超时；run 是同步执行（逐插件真实调用），单独放大超时到 10 分钟
export const llmTestTaskList = () => http.get('/v1/llmTest/task/list')
export const llmTestTaskGet = (id) => http.get(`/v1/llmTest/task/get/${id}`)
export const llmTestTaskAdd = (payload) => http.post('/v1/llmTest/task/add', payload)
export const llmTestTaskUpdate = (id, payload) => http.post(`/v1/llmTest/task/update/${id}`, payload)
export const llmTestTaskDelete = (id) => http.post(`/v1/llmTest/task/delete/${id}`)
export const llmTestTaskRun = (id) => http.post(`/v1/llmTest/task/run/${id}`, null, { timeout: 600000 })
// PDF 下载：blob 响应（拦截器对无 code 字段的响应原样返回）
export const llmTestReportPdf = (id) => http.get(`/v1/llmTest/task/report/${id}/pdf`, { responseType: 'blob' })

// 一键测试：全部任务后台串行运行，提交后轮询进度
export const llmTestRunAll = () => http.post('/v1/llmTest/task/runAll')
export const llmTestRunAllStatus = () => http.get('/v1/llmTest/runAll/status')

// 历史测试记录：每次运行留档，可回看任意一次的完整报告与 PDF
export const llmTestTaskRuns = (id, params) => http.get(`/v1/llmTest/task/runs/${id}`, { params })
export const llmTestRunGet = (runId) => http.get(`/v1/llmTest/run/get/${runId}`)
export const llmTestRunPdf = (runId) => http.get(`/v1/llmTest/run/${runId}/pdf`, { responseType: 'blob' })

// ===================== 知识库（ragflow，自研模块：ES 混合检索 + MinIO + 向量化）=====================
export const kbEmbeddingModels = () => http.get('/v1/kb/embeddingModels')
export const kbParserMethods = () => http.get('/v1/kb/parserMethods')
export const kbList = () => http.get('/v1/kb/list')
export const kbGet = (id) => http.get(`/v1/kb/get/${id}`)
export const kbAdd = (payload) => http.post('/v1/kb/add', payload)
export const kbUpdate = (id, payload) => http.post(`/v1/kb/update/${id}`, payload)
export const kbDelete = (id) => http.post(`/v1/kb/delete/${id}`)
export const kbDocList = (kbId, params) => http.get(`/v1/kb/${kbId}/document/list`, { params })
// 上传走 multipart；解析为后台任务，前端轮询 document/list 的 run/progress
export const kbDocUpload = (kbId, formData) =>
  http.post(`/v1/kb/${kbId}/document/upload`, formData, { timeout: 120000 })
// parser_id 走查询参数（后端 Form 兼容 query），不传则继承知识库默认切片方法
export const kbDocUploadWithParser = (kbId, formData, parserId) =>
  http.post(`/v1/kb/${kbId}/document/upload${parserId ? `?parser_id=${encodeURIComponent(parserId)}` : ''}`,
    formData, { timeout: 120000 })
export const kbDocParse = (docId) => http.post(`/v1/kb/document/parse/${docId}`)
export const kbDocParser = (docId, parserId) => http.post(`/v1/kb/document/parser/${docId}`, { parser_id: parserId })
export const kbDocAvailable = (docId, available) => http.post(`/v1/kb/document/available/${docId}`, { available })
export const kbDocDelete = (docId) => http.post(`/v1/kb/document/delete/${docId}`)
export const kbChunkList = (kbId, params) => http.get(`/v1/kb/${kbId}/chunk/list`, { params })
// 检索为同步接口（含 embedding 往返），超时放宽
export const kbRetrieval = (payload) => http.post('/v1/kb/retrieval', payload, { timeout: 60000 })

// 对外 API Key 管理（JWT 鉴权，用户管理自己的 key）
// 账号级 API Key（模块无关，各模块开放接口共用，管理挂 user 下）
export const apiKeyList = () => http.get('/v1/user/apikey/list')
export const apiKeyAdd = (payload) => http.post('/v1/user/apikey/add', payload)
export const apiKeyStatus = (id, status) => http.post(`/v1/user/apikey/status/${id}?status=${status}`)
export const apiKeyDelete = (id) => http.post(`/v1/user/apikey/delete/${id}`)
