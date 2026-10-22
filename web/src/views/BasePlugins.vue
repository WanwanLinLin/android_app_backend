<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title">
          <el-icon><Grid /></el-icon>基础插件
          <span class="count-chip">{{ total }}</span>
        </div>
        <div class="toolbar-right">
          <el-input v-model="keyword" placeholder="搜索名称 / 描述" clearable
                    :prefix-icon="Search" style="width: 240px" />
          <el-button :icon="Refresh" round plain @click="load">刷新</el-button>
          <el-button v-if="auth.isAdmin" type="primary" round @click="openAdd">
            <el-icon style="margin-right:4px"><Plus /></el-icon>登记插件
          </el-button>
        </div>
      </div>
      <div class="tip-bar">
        <el-icon><InfoFilled /></el-icon>
        基础插件对应 utils/providers 目录下的代码文件（列表刷新时自动扫描登记）。
        下架为<b>严格全面禁用</b>：基于它的个性插件连带隐藏，已绑定租户的会话将直接拒绝。
      </div>
      <div v-if="!auth.isAdmin" class="readonly-tip">
        <el-icon><InfoFilled /></el-icon>
        基础插件仅管理员可登记、修改、上下架；你可在「个性插件」中基于在售插件创建自己的配置
      </div>

      <el-table :data="paged" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="90">
          <template #default="{ row }">
            <span class="type-chip" :style="{ '--accent': catColor(row.category) }">
              <el-icon :size="13"><component :is="catIcon(row.category)" /></el-icon>{{ row.category }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="插件名" min-width="150">
          <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column prop="desc" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column prop="custom_count" label="个性插件" width="90" align="center" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'off_shelf'" type="warning" size="small" effect="light">已下架</el-tag>
            <el-tag v-else type="success" size="small" effect="light">在售</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column v-if="auth.isAdmin" label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" round plain
                       :type="row.status === 'off_shelf' ? 'success' : 'warning'"
                       @click="onShelfToggle(row)">
              {{ row.status === 'off_shelf' ? '上架' : '下架' }}
            </el-button>
            <el-button size="small" round plain type="danger" @click="onDelete(row)">注销</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>{{ keyword ? '没有匹配的插件' : '暂无插件（放入代码文件后点刷新自动登记）' }}</p>
          </div>
        </template>
      </el-table>

      <div class="pager" v-if="filtered.length">
        <el-pagination background layout="total, sizes, prev, pager, next"
                       :total="filtered.length" v-model:current-page="page" v-model:page-size="pageSize"
                       :page-sizes="[10, 20, 50, 100]" />
      </div>
    </div>

    <!-- 登记 / 编辑 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑基础插件' : '登记基础插件'"
               width="560px" destroy-on-close append-to-body>
      <el-form :model="form" label-width="130px" ref="formRef">
        <el-form-item label="类别" prop="category" :rules="[{ required: true, message: '类别不能为空', trigger: 'change' }]">
          <el-select v-model="form.category" :disabled="!!editing" style="width: 100%">
            <el-option label="TTS" value="TTS" /><el-option label="ASR" value="ASR" /><el-option label="LLM" value="LLM" />
          </el-select>
        </el-form-item>
        <el-form-item label="插件名" prop="name" :rules="[{ required: true, message: '插件名不能为空', trigger: 'blur' }]">
          <el-input v-model="form.name" :disabled="!!editing"
                    placeholder="utils/providers 下的文件名（不含 .py），如 openai" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.desc" placeholder="简短描述，供普通用户识别" />
        </el-form-item>
        <!-- 默认参数仅登记时可填；编辑不开放——运行时参数只在个性插件层改 params -->
        <el-form-item v-if="!editing" label="默认参数(JSON)">
          <JsonEditor v-model="form.default_config" :reset-value="jsonReset.default_config || ''" />
          <div class="field-hint">创建个性插件时预填的参数模板，与运行时无关</div>
        </el-form-item>
        <el-form-item v-else label="默认参数">
          <pre v-if="editing.default_config" class="config-pre">{{ prettyConfig(editing.default_config) }}</pre>
          <span v-else class="muted">—</span>
          <div class="field-hint">默认参数登记后不可修改；运行时参数请在个性插件中编辑 params</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 下架影响面 -->
    <el-dialog v-model="shelfVisible" title="下架影响面" width="620px" destroy-on-close append-to-body>
      <div v-loading="shelfLoading">
        <div class="shelf-summary">
          <el-icon><InfoFilled /></el-icon>
          <span v-if="shelfData.custom_count === 0">还没有基于该插件的个性插件，可安全下架。</span>
          <span v-else>有 <b>{{ shelfData.custom_count }}</b> 个基于它的个性插件，共
            <b :class="{ danger: shelfData.bound_count > 0 }">{{ shelfData.bound_count }}</b> 条租户绑定。</span>
        </div>
        <el-alert v-if="shelfData.warning" type="error" :closable="false" show-icon
                  :title="shelfData.warning" style="margin-bottom: 12px" />
        <el-table v-if="shelfData.customs && shelfData.customs.length" :data="shelfData.customs"
                  size="small" max-height="240" stripe>
          <el-table-column prop="name" label="个性插件" />
          <el-table-column label="归属" width="110">
            <template #default="{ row }">
              <span class="muted">{{ row.owner_id ? `用户#${row.owner_id}` : '平台' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bound_count" label="租户绑定" width="90" align="center" />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="shelfVisible = false">取消</el-button>
        <el-button type="danger" :loading="shelfSubmitting"
                   :disabled="shelfLoading" @click="confirmOffShelf">确认下架（严格禁用）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, Box, Grid, InfoFilled, Microphone, ChatDotSquare, MagicStick } from '@element-plus/icons-vue'
import { basePluginList, basePluginAdd, basePluginUpdate, basePluginDelete,
         basePluginOffShelfPreview, basePluginOffShelf, basePluginOnShelf } from '@/api'
import JsonEditor from '@/components/JsonEditor.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')

const catColor = (c) => ({ TTS: '#6366f1', ASR: '#0ea5e9', LLM: '#8b5cf6' }[c] || '#909399')
const catIcon = (c) => ({ TTS: Microphone, ASR: ChatDotSquare, LLM: MagicStick }[c] || Box)

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter((r) => [r.name, r.desc, r.category].some(
    (v) => typeof v === 'string' && v.toLowerCase().includes(k)))
})

// 前端分页：数据量小（插件登记全量返回），按 filtered 切片展示
const page = ref(1)
const pageSize = ref(10)
const paged = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})
// 搜索词变化后回到第一页，避免停留在超出范围的页码上
watch(keyword, () => { page.value = 1 })

async function load() {
  loading.value = true
  try {
    const data = await basePluginList()
    rows.value = data.rows || []
    total.value = data.total || rows.value.length
    // 保持当前页（编辑保存后的静默刷新不跳页）；数据变少导致越界时钳制到最后一页
    const maxPage = Math.max(1, Math.ceil(rows.value.length / pageSize.value))
    if (page.value > maxPage) page.value = maxPage
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// ===================== 登记 / 编辑 =====================
const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editing = ref(null)
const form = reactive({ category: 'TTS', name: '', desc: '', default_config: '' })
const jsonReset = reactive({ default_config: '' })

function openAdd() {
  editing.value = null
  form.category = 'TTS'; form.name = ''; form.desc = ''; form.default_config = ''
  jsonReset.default_config = ''
  formVisible.value = true
}

function openEdit(row) {
  editing.value = row
  form.category = row.category
  form.name = row.name
  form.desc = row.desc || ''
  form.default_config = ''
  jsonReset.default_config = ''
  formVisible.value = true
}

// 编辑态只读展示默认参数（登记后不可改）
function prettyConfig(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  try { return JSON.stringify(JSON.parse(v), null, 2) } catch (e) { return String(v) }
}

async function submitForm() {
  await formRef.value.validate().catch(() => { throw new Error('请检查必填项') })
  submitting.value = true
  try {
    if (editing.value) {
      // 编辑仅提交 desc；default_config 登记后不再开放修改
      await basePluginUpdate(editing.value.id, { desc: form.desc || null })
      ElMessage.success('更新成功')
    } else {
      let defaultConfig = null
      if (form.default_config !== '' && form.default_config !== null) {
        try { defaultConfig = JSON.parse(form.default_config) }
        catch (e) { ElMessage.error('默认参数不是合法 JSON'); return }
      }
      await basePluginAdd({ category: form.category, name: form.name, desc: form.desc || null, default_config: defaultConfig })
      ElMessage.success('登记成功')
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
    await ElMessageBox.confirm(
      `确认注销「${row.name}」？仅移除登记并禁用，不删除磁盘代码文件；若仍有基于它的个性插件会被拒绝。`,
      '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await basePluginDelete(row.id)
    ElMessage.success('已注销')
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
    try {
      await basePluginOnShelf(row.id)
      ElMessage.success('已上架')
      await load()
    } catch (e) { ElMessage.error(e.message) }
    return
  }
  shelfRow.value = row
  shelfData.value = {}
  shelfVisible.value = true
  shelfLoading.value = true
  try {
    shelfData.value = await basePluginOffShelfPreview(row.id)
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
    await basePluginOffShelf(shelfRow.value.id)
    ElMessage.success('已下架（基于它的个性插件已连带禁用）')
    shelfVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    shelfSubmitting.value = false
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
.tip-bar, .readonly-tip {
  display: flex; align-items: center; gap: 6px;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.06), transparent);
  border-left: 3px solid #6366f1;
  color: #5a607a; font-size: 12px; padding: 8px 12px; border-radius: 8px; margin-bottom: 14px;
}
.readonly-tip { background: linear-gradient(90deg, rgba(245, 158, 11, 0.08), transparent); border-left-color: #f59e0b; color: #92640a; }
.tip-bar b { color: #d0453e; }
.mono { font-family: ui-monospace, "SF Mono", Consolas, monospace; color: #6366f1; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
.type-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, white);
  border: 1px solid color-mix(in srgb, var(--accent) 28%, white);
}
.field-hint { font-size: 11.5px; color: #98a0b3; margin-top: 4px; }
.config-pre {
  margin: 0; width: 100%; max-height: 260px; overflow: auto;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px; line-height: 1.55; color: #3b3f52;
  background: #f6f7fb; border: 1px solid #e6e9f2; border-radius: 8px;
  padding: 10px 12px; white-space: pre-wrap; word-break: break-all;
}
.shelf-summary {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 13px; color: #3b3f52; margin-bottom: 12px; line-height: 1.6;
}
.shelf-summary .el-icon { color: #6366f1; margin-top: 2px; }
.shelf-summary b { color: #6366f1; }
.shelf-summary b.danger { color: #f56c6c; }
.muted { color: #8a90a5; }
</style>
