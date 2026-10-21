<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title">
          <el-icon><component :is="typeIcon" /></el-icon>{{ meta.label }}
          <span class="count-chip">{{ total }}</span>
        </div>
        <div class="toolbar-right">
          <el-input v-model="keyword" placeholder="搜索描述 / 标签 / 地址" clearable
                    :prefix-icon="Search" style="width: 240px" />
          <el-button :icon="Refresh" round plain @click="load">刷新</el-button>
          <el-button v-if="auth.isAdmin" type="primary" round @click="openAdd">
            <el-icon style="margin-right:4px"><Plus /></el-icon>新增{{ meta.label }}
          </el-button>
        </div>
      </div>
      <div v-if="!auth.isAdmin" class="readonly-tip">
        <el-icon><InfoFilled /></el-icon>
        资源池为全局共享数据，仅管理员可新增、编辑或删除；你可以查看并绑定到自己名下的租户
      </div>
      <div v-if="meta.getNeedsAccesskey" class="ak-tip">
        <el-icon><Lock /></el-icon>
        查看详情走对称加密接口：请求头 dk=毫秒时间戳，token=SHA1(时间戳\tAPP_KEY)，由前端 crypto-js 实时计算
      </div>

      <el-table :data="filtered" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column v-for="f in tableFields" :key="f.key" :prop="f.key" :label="f.label"
                         :show-overflow-tooltip="true" min-width="120">
          <template #default="{ row }">{{ display(row[f.key]) }}</template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建时间" width="170" />
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'off_shelf'" type="warning" size="small" effect="light">已下架</el-tag>
            <el-tag v-else type="success" size="small" effect="light">在售</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" :width="auth.isAdmin ? 300 : 100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain @click="openView(row)">
              <el-icon style="margin-right:3px"><View /></el-icon>查看
            </el-button>
            <el-button v-if="auth.isAdmin" size="small" round plain type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="auth.isAdmin" size="small" round plain
                       :type="row.status === 'off_shelf' ? 'success' : 'warning'"
                       @click="onShelfToggle(row)">
              {{ row.status === 'off_shelf' ? '上架' : '下架' }}
            </el-button>
            <el-button v-if="auth.isAdmin" size="small" round plain type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>{{ keyword ? '没有匹配的资源' : (auth.isAdmin ? '暂无资源，点击右上角新增' : '暂无资源') }}</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑' + meta.label : '新增' + meta.label"
               width="560px" destroy-on-close append-to-body>
      <el-form :model="form" label-width="130px" ref="formRef">
        <el-form-item v-for="f in meta.fields" :key="f.key" :label="f.label"
                      :prop="f.key" :rules="f.required ? [{ required: true, message: f.label + '不能为空', trigger: 'blur' }] : []">
          <JsonEditor v-if="f.type === 'json'" v-model="form[f.key]"
                      :reset-value="jsonReset[f.key] || ''" />
          <el-input v-else-if="f.type === 'textarea'" v-model="form[f.key]" type="textarea" :rows="8"
                    :placeholder="f.placeholder || ''" />
          <el-input v-else v-model="form[f.key]" :placeholder="f.placeholder || ''" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 下架影响面预览 -->
    <el-dialog v-model="shelfVisible" title="下架影响面" width="600px" destroy-on-close append-to-body>
      <div v-loading="shelfLoading">
        <div class="shelf-summary">
          <el-icon><InfoFilled /></el-icon>
          <span v-if="shelfData.bound_count === 0">该资源当前没有被任何租户绑定，可安全下架。</span>
          <span v-else>该资源已被 <b>{{ shelfData.bound_count }}</b> 个租户绑定，其中
            <b :class="{ danger: shelfData.default_count > 0 }">{{ shelfData.default_count }}</b> 个将其设为默认资源。</span>
        </div>
        <div v-if="shelfData.warning" class="shelf-warning">
          <el-icon><WarningFilled /></el-icon>{{ shelfData.warning }}
        </div>
        <el-alert v-if="shelfData.bound_count > 0" type="info" :closable="false" show-icon
                  title="下架只关闭新增绑定与设为默认的入口，已绑定的租户照常可用；删除才会中断存量。"
                  style="margin-bottom: 12px" />
        <el-table v-if="shelfData.tenants && shelfData.tenants.length" :data="shelfData.tenants"
                  size="small" max-height="240" stripe>
          <el-table-column prop="tenantname" label="租户" />
          <el-table-column label="默认资源" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" type="danger" size="small">默认</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="shelfVisible = false">取消</el-button>
        <el-button type="warning" :loading="shelfSubmitting"
                   :disabled="shelfLoading" @click="confirmOffShelf">确认下架</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情 -->
    <el-dialog v-model="viewVisible" title="资源详情" :width="detail.content ? '760px' : '560px'" append-to-body>
      <el-descriptions :column="1" border v-loading="viewing">
        <el-descriptions-item v-for="(v, k) in detail" :key="k" :label="k">
          <!-- content 为协议文档全文：JSON 时格式化缩进展示，用可滚动 pre 保留排版 -->
          <pre v-if="k === 'content' && v" class="content-pre">{{ prettyContent(v) }}</pre>
          <span v-else-if="k !== 'content'">{{ display(v) }}</span>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
      </el-descriptions>
      <!-- 连通性检测结果：成功/失败摘要 + 目标与耗时 -->
      <div v-if="checkResult" class="check-result" :class="checkResult.reachable ? 'ok' : 'fail'">
        <el-icon><component :is="checkResult.reachable ? CircleCheck : CircleClose" /></el-icon>
        <template v-if="checkResult.reachable">
          连通正常：<span class="mono">{{ checkResult.host }}:{{ checkResult.port }}</span>
          TCP 建连耗时 {{ checkResult.latency_ms }} ms
        </template>
        <template v-else>
          无法连通：<span class="mono">{{ checkResult.host }}:{{ checkResult.port }}</span>
          {{ checkResult.error }}
        </template>
      </div>
      <template #footer>
        <el-button v-if="detail.url" :loading="checking" @click="onCheckConnect">
          <el-icon style="margin-right:3px"><Connection /></el-icon>检测连通性
        </el-button>
        <el-button type="primary" @click="viewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, View, Box, Microphone, ChatDotSquare, MagicStick, Document, Lock, InfoFilled, WarningFilled, Connection, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { resourceList, resourceAdd, resourceGet, resourceUpdate, resourceDelete, resourceOffShelfPreview, resourceOffShelf, resourceOnShelf, connectCheck } from '@/api'
import { RES_FIELDS } from './resFields'
import JsonEditor from '@/components/JsonEditor.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const props = defineProps({ resType: { type: String, required: true } })
const meta = computed(() => RES_FIELDS[props.resType])
// 表格列：跳过 hideInTable 的长文本字段（如对话模板 content 协议文档）
const tableFields = computed(() => meta.value.fields.filter((f) => !f.hideInTable))
const typeIcon = computed(() => ({
  TTS: Microphone, ASR: ChatDotSquare, LLM: MagicStick, CHATTEMPLATE: Document
}[props.resType] || Box))

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')

const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editing = ref(null)
const form = reactive({})
// JSON 字段的初始原文（供 JsonEditor「重置」回到打开弹窗时的值）
const jsonReset = reactive({})

const viewVisible = ref(false)
const viewing = ref(false)
const detail = ref({})

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter((r) =>
    Object.values(r).some((v) => typeof v === 'string' && v.toLowerCase().includes(k)))
})

function display(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return v
}

// 协议文档内容：能解析为 JSON 就缩进 2 格美化，否则原样展示
function prettyContent(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  try {
    return JSON.stringify(JSON.parse(v), null, 2)
  } catch (e) {
    return String(v)
  }
}

async function load() {
  loading.value = true
  try {
    const data = await resourceList(props.resType)
    rows.value = data.rows || []
    total.value = data.total || rows.value.length
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function resetForm(row) {
  meta.value.fields.forEach((f) => {
    let v = row ? row[f.key] : ''
    if (f.type === 'json') v = (v && typeof v === 'object') ? JSON.stringify(v, null, 2) : (v || '')
    form[f.key] = v === null || v === undefined ? '' : v
    if (f.type === 'json') jsonReset[f.key] = form[f.key]
  })
}

function openAdd() {
  editing.value = null
  meta.value.fields.forEach((f) => { form[f.key] = '' })
  formVisible.value = true
}

function openEdit(row) {
  editing.value = row
  resetForm(row)
  formVisible.value = true
}

function buildPayload() {
  const payload = {}
  for (const f of meta.value.fields) {
    const raw = form[f.key]
    if (f.type === 'json') {
      if (raw === '' || raw === null || raw === undefined) {
        if (f.required) throw new Error(`${f.label}不能为空`)
        continue
      }
      try {
        payload[f.key] = JSON.parse(raw)
      } catch (e) {
        throw new Error(`${f.label}不是合法 JSON`)
      }
    } else {
      if (raw === '' || raw === null) {
        if (f.required) throw new Error(`${f.label}不能为空`)
        continue
      }
      payload[f.key] = raw
    }
  }
  return payload
}

async function submitForm() {
  await formRef.value.validate().catch(() => { throw new Error('请检查必填项') })
  let payload
  try {
    payload = buildPayload()
  } catch (e) {
    ElMessage.error(e.message)
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await resourceUpdate(props.resType, editing.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await resourceAdd(props.resType, payload)
      ElMessage.success('新增成功')
    }
    formVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ID=${row.id} 的${meta.value.label}？仍有租户绑定会被拒绝（停用请改用下架）`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await resourceDelete(props.resType, row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ===================== 上下架 =====================
const shelfVisible = ref(false)
const shelfLoading = ref(false)
const shelfSubmitting = ref(false)
const shelfData = ref({})
const shelfRow = ref(null)

async function onShelfToggle(row) {
  if (row.status === 'off_shelf') {
    // 上架无条件安全，直接执行
    try {
      await resourceOnShelf(props.resType, row.id)
      ElMessage.success('已上架')
      await load()
    } catch (e) {
      ElMessage.error(e.message)
    }
    return
  }
  // 下架先看影响面，管理员确认后才执行
  shelfRow.value = row
  shelfData.value = {}
  shelfVisible.value = true
  shelfLoading.value = true
  try {
    shelfData.value = await resourceOffShelfPreview(props.resType, row.id)
  } catch (e) {
    ElMessage.error(e.message)
    shelfVisible.value = false
  } finally {
    shelfLoading.value = false
  }
}

async function confirmOffShelf() {
  shelfSubmitting.value = true
  try {
    await resourceOffShelf(props.resType, shelfRow.value.id)
    ElMessage.success('已下架，存量绑定不受影响')
    shelfVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    shelfSubmitting.value = false
  }
}

const checking = ref(false)
const checkResult = ref(null)

async function openView(row) {
  viewVisible.value = true
  viewing.value = true
  detail.value = {}
  checkResult.value = null
  try {
    detail.value = await resourceGet(props.resType, row.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    viewing.value = false
  }
}

// 资源连通性检测：把资源 url 交给后端做 TCP 建连探测（ip:端口 / 域名均可）
async function onCheckConnect() {
  checking.value = true
  checkResult.value = null
  try {
    checkResult.value = await connectCheck({ url: detail.value.url })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    checking.value = false
  }
}

onMounted(load)

// TTS/ASR/LLM/CHATTEMPLATE 四条路由复用本组件，路由切换时组件实例被复用、
// onMounted 不再触发，导致切换后仍显示上一个资源类型的旧数据。
// 监听 resType 变化，重置状态并重新拉取。
watch(() => props.resType, () => {
  rows.value = []
  total.value = 0
  keyword.value = ''
  formVisible.value = false
  viewVisible.value = false
  load()
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; gap: 10px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 10px; align-items: center; margin-left: auto; }
.card-title { display: flex; align-items: center; gap: 7px; font-size: 15px; font-weight: 650; color: #3b3f52; }
.card-title .el-icon { color: #6366f1; }
.count-chip {
  background: linear-gradient(135deg, #6366f1, #06b6d4); color: #fff;
  font-size: 11.5px; padding: 1px 9px; border-radius: 999px; font-weight: 600;
}
.ak-tip {
  display: flex; align-items: center; gap: 6px;
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.08), transparent);
  border-left: 3px solid #f59e0b;
  color: #92640a; font-size: 12px; padding: 8px 12px; border-radius: 8px; margin-bottom: 14px;
}
.mono { font-family: ui-monospace, "SF Mono", Consolas, monospace; color: #6366f1; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
.shelf-summary {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 13px; color: #3b3f52; margin-bottom: 12px; line-height: 1.6;
}
.shelf-summary .el-icon { color: #6366f1; margin-top: 2px; }
.shelf-summary b { color: #6366f1; }
.shelf-summary b.danger { color: #f56c6c; }
.shelf-warning {
  display: flex; align-items: flex-start; gap: 6px;
  background: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b;
  color: #92640a; font-size: 12px; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px;
}
.muted { color: #c0c6d9; }
.check-result {
  display: flex; align-items: center; gap: 7px; margin-top: 12px;
  font-size: 13px; padding: 9px 12px; border-radius: 8px; line-height: 1.5;
}
.check-result.ok { background: rgba(103, 194, 58, 0.09); border-left: 3px solid #67c23a; color: #3f6b2a; }
.check-result.fail { background: rgba(245, 108, 108, 0.08); border-left: 3px solid #f56c6c; color: #a04040; }
.check-result .el-icon { margin-top: 1px; }
.content-pre {
  margin: 0; max-height: 420px; overflow: auto;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px; line-height: 1.55; color: #3b3f52;
  background: #f6f7fb; border: 1px solid #e6e9f2; border-radius: 8px;
  padding: 10px 12px; white-space: pre-wrap; word-break: break-all;
}
</style>
