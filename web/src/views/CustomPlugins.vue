<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title">
          <el-icon><MagicStick /></el-icon>{{ catLabel }}个性插件
          <span class="count-chip">{{ total }}</span>
        </div>
        <div class="toolbar-right">
          <el-radio-group v-model="category" @change="onCatChange">
            <el-radio-button value="TTS">TTS</el-radio-button>
            <el-radio-button value="ASR">ASR</el-radio-button>
            <el-radio-button value="LLM">LLM</el-radio-button>
          </el-radio-group>
          <el-input v-model="keyword" placeholder="搜索名称 / 描述" clearable
                    :prefix-icon="Search" style="width: 200px" />
          <el-button :icon="Refresh" round plain @click="load">刷新</el-button>
          <el-button type="primary" round @click="openAdd">
            <el-icon style="margin-right:4px"><Plus /></el-icon>新建个性插件
          </el-button>
        </div>
      </div>
      <div class="tip-bar">
        <el-icon><InfoFilled /></el-icon>
        在基础插件之上定义自己的完整配置（JSON），仅自己可见可绑定到租户；
        基础插件被下架后，基于它的个性插件将连带不可见、不可绑定。
      </div>

      <el-table :data="paged" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="base_plugin_name" label="基础插件" width="160">
          <template #default="{ row }"><span class="mono">{{ row.base_plugin_name }}</span></template>
        </el-table-column>
        <el-table-column prop="desc" label="描述" min-width="160" show-overflow-tooltip />
        <el-table-column v-if="auth.isAdmin" label="归属" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.owner_id === auth.id" size="small" effect="light" type="success">我的</el-tag>
            <span v-else class="muted">用户#{{ row.owner_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column label="操作" :width="hasEditable ? 230 : 100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain @click="openView(row)">
              <el-icon style="margin-right:3px"><View /></el-icon>查看
            </el-button>
            <el-button v-if="canEdit(row)" size="small" round plain type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canDelete(row)" size="small" round plain type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>{{ keyword ? '没有匹配的插件' : '暂无个性插件，点击右上角基于基础插件创建一个' }}</p>
          </div>
        </template>
      </el-table>

      <div class="pager" v-if="filtered.length">
        <el-pagination background layout="total, sizes, prev, pager, next"
                       :total="filtered.length" v-model:current-page="page" v-model:page-size="pageSize"
                       :page-sizes="[10, 20, 50, 100]" />
      </div>
    </div>

    <!-- 新建 / 编辑 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑个性插件' : '新建个性插件'"
               width="640px" destroy-on-close append-to-body>
      <el-form :model="form" label-width="120px" ref="formRef">
        <el-form-item label="名称" prop="name" :rules="editing ? [] : [{ required: true, message: '名称不能为空', trigger: 'blur' }]">
          <el-input v-if="!editing" v-model="form.name" placeholder="如：客服音色-温柔女声" />
          <span v-else>{{ editing.name }}</span>
        </el-form-item>
        <el-form-item v-if="editing" label="描述">
          <span class="muted">{{ editing.desc || '—' }}</span>
        </el-form-item>
        <el-form-item v-if="!editing" label="描述">
          <el-input v-model="form.desc" placeholder="简短描述（可选）" />
        </el-form-item>
        <el-form-item v-if="!editing" label="基础插件" prop="base_plugin_id"
                      :rules="[{ required: true, message: '请选择基础插件', trigger: 'change' }]">
          <el-select v-model="form.base_plugin_id" style="width: 100%" @change="onBaseChange"
                     placeholder="选择在售的基础插件">
            <el-option v-for="b in bases" :key="b.id" :value="b.id"
                       :label="`${b.name}${b.desc ? ' · ' + b.desc : ''}`" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editing" label="基础插件">
          <span class="mono">{{ editing.base_plugin_name }}</span>
        </el-form-item>
        <!-- 新建 / 编辑：完整配置 JSON（保存时后端按类别模板校验必含键） -->
        <el-form-item label="完整配置(JSON)" prop="config" :rules="[{ required: true, message: '配置不能为空', trigger: 'blur' }]">
          <JsonEditor v-model="form.config" :reset-value="jsonReset.config || ''" />
          <div class="field-hint">
            必含参数：<span class="mono">{{ templateKeys }}</span>
            <template v-if="category === 'TTS'">；tag 须为登记在册且在售的 TTS 基础插件名（缺省用基础插件名）</template>
            <template v-else>；type 由基础插件强制，无需填写</template>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情 -->
    <el-dialog v-model="viewVisible" title="个性插件详情" width="640px" append-to-body>
      <el-descriptions :column="1" border v-loading="viewing">
        <el-descriptions-item v-for="(v, k) in detail" :key="k" :label="k">
          <pre v-if="k === 'config' && v" class="content-pre">{{ pretty(v) }}</pre>
          <span v-else>{{ display(v) }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="viewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, View, Box, MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { customPluginList, customPluginGet, customPluginAdd, customPluginUpdate,
         customPluginDelete, basePluginList } from '@/api'
import JsonEditor from '@/components/JsonEditor.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const category = ref('TTS')
const catLabel = computed(() => ({ TTS: 'TTS', ASR: 'ASR', LLM: 'LLM' }[category.value]))

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const bases = ref([])

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter((r) => [r.name, r.desc, r.base_plugin_name].some(
    (v) => typeof v === 'string' && v.toLowerCase().includes(k)))
})

// 前端分页：接口按类别全量返回，前端按 filtered 切片展示
const page = ref(1)
const pageSize = ref(10)
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})
// 切换类别/搜索词变化后回到第一页
watch(keyword, () => { page.value = 1 })

// 严格私有：只有创建者本人（owner_id===自己）能编辑/删除自己的个性插件。
// admin 列表可见全部但改删仍限本人（与后端 custom_plugin_orm 同口径）。
const canEdit = (row) => row && row.owner_id != null && row.owner_id === auth.id
const canDelete = canEdit
// 操作列宽度：当前列表里只要存在自己创建的插件就加宽（编辑/删除按钮可用时）
const hasEditable = computed(() => rows.value.some((r) => canEdit(r)))

// 切换类别是用户主动行为，回第一页再加载
function onCatChange() {
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const data = await customPluginList(category.value)
    rows.value = data.rows || []
    total.value = data.total || rows.value.length
    // 保持当前页（编辑保存后的静默刷新不跳页）；数据变少导致越界时钳制到最后一页
    const maxPage = Math.max(1, Math.ceil(rows.value.length / pageSize.value))
    if (page.value > maxPage) page.value = maxPage
    // 在售基础插件（供新建下拉；admin 返回全量，前端只取在售项）
    const bp = await basePluginList()
    bases.value = (bp.rows || []).filter((b) => b.category === category.value && b.status !== 'off_shelf')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// ===================== 新建 / 编辑 =====================
const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editing = ref(null)
const form = reactive({ name: '', desc: '', base_plugin_id: null, config: '' })
const jsonReset = reactive({ config: '' })

// 各类别个性插件 config 必含键模板（与后端 CONFIG_TEMPLATE 同口径，仅提示用途，
// 权威校验在后端保存时执行）
const CONFIG_TEMPLATES = {
  TTS: ['url', 'tag', 'voice', 'apikey', 'params'],
  ASR: ['url', 'apikey', 'params'],
  LLM: ['url', 'apikey', 'params'],
}
const templateKeys = computed(() => (CONFIG_TEMPLATES[category.value] || []).join(' | '))

function openAdd() {
  editing.value = null
  form.name = ''; form.desc = ''; form.base_plugin_id = null
  form.config = '{}'
  jsonReset.config = '{}'
  formVisible.value = true
}

// 切换基础插件时，用其默认参数模板预填 config；
// 基础插件无模板时按类别必含键预填空骨架（type 由后端强制，不预填）
function onBaseChange(id) {
  const b = bases.value.find((x) => x.id === id)
  let tpl
  if (b && b.default_config && Object.keys(b.default_config).length) {
    tpl = JSON.stringify(b.default_config, null, 2)
  } else {
    const keys = CONFIG_TEMPLATES[category.value] || []
    const obj = {}
    keys.forEach((k) => { obj[k] = k === 'params' ? {} : '' })
    tpl = JSON.stringify(obj, null, 2)
  }
  form.config = tpl
  jsonReset.config = tpl
}

function openEdit(row) {
  editing.value = row
  form.name = row.name
  form.desc = row.desc || ''
  // 编辑开放完整 config；type / id 由后端强制生成，从编辑器中剔除避免误导
  const cfg = { ...(row.config || {}) }
  delete cfg.type
  delete cfg.id
  form.config = JSON.stringify(cfg, null, 2)
  jsonReset.config = form.config
  formVisible.value = true
}

// 保存前的本地模板校验（与后端 CONFIG_TEMPLATE 同口径，双保险）
function checkTemplate(config) {
  const keys = CONFIG_TEMPLATES[category.value] || []
  const missing = keys.filter((k) => !(k in config))
  if (missing.length) {
    ElMessage.error(`配置缺少必含参数：${missing.join(' | ')}（模板要求：${keys.join(' | ')}）`)
    return false
  }
  return true
}

async function submitForm() {
  await formRef.value.validate().catch(() => { throw new Error('请检查必填项') })
  submitting.value = true
  try {
    let config
    try { config = JSON.parse(form.config || '{}') }
    catch (e) { ElMessage.error('配置不是合法 JSON'); return }
    if (!checkTemplate(config)) return
    if (editing.value) {
      await customPluginUpdate(editing.value.id, { config })
      ElMessage.success('更新成功')
    } else {
      const payload = { name: form.name, desc: form.desc || null, base_plugin_id: form.base_plugin_id, config }
      await customPluginAdd(payload)
      ElMessage.success('创建成功')
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
    await ElMessageBox.confirm(`确认删除个性插件「${row.name}」？仍有租户绑定会被拒绝。`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await customPluginDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ===================== 查看详情 =====================
const viewVisible = ref(false)
const viewing = ref(false)
const detail = ref({})

function display(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return v
}
function pretty(v) {
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  try { return JSON.stringify(JSON.parse(v), null, 2) } catch (e) { return String(v) }
}

async function openView(row) {
  viewVisible.value = true
  viewing.value = true
  detail.value = {}
  try {
    detail.value = await customPluginGet(row.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    viewing.value = false
  }
}

onMounted(load)
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
.tip-bar {
  display: flex; align-items: center; gap: 6px;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.06), transparent);
  border-left: 3px solid #6366f1;
  color: #5a607a; font-size: 12px; padding: 8px 12px; border-radius: 8px; margin-bottom: 14px;
}
.mono { font-family: ui-monospace, "SF Mono", Consolas, monospace; color: #6366f1; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
.muted { color: #8a90a5; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
.field-hint { font-size: 11.5px; color: #98a0b3; }
.content-pre {
  margin: 0; max-height: 420px; overflow: auto;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px; line-height: 1.55; color: #3b3f52;
  background: #f6f7fb; border: 1px solid #e6e9f2; border-radius: 8px;
  padding: 10px 12px; white-space: pre-wrap; word-break: break-all;
}
</style>
