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
        <el-table-column v-for="f in meta.fields" :key="f.key" :prop="f.key" :label="f.label"
                         :show-overflow-tooltip="true" min-width="120">
          <template #default="{ row }">{{ display(row[f.key]) }}</template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建时间" width="170" />
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column label="操作" :width="auth.isAdmin ? 230 : 100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain @click="openView(row)">
              <el-icon style="margin-right:3px"><View /></el-icon>查看
            </el-button>
            <el-button v-if="auth.isAdmin" size="small" round plain type="primary" @click="openEdit(row)">编辑</el-button>
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
          <el-input v-if="f.type === 'json'" v-model="form[f.key]" type="textarea" :rows="4"
                    :placeholder="f.placeholder || '请输入合法 JSON'" />
          <el-input v-else v-model="form[f.key]" :placeholder="f.placeholder || ''" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看详情 -->
    <el-dialog v-model="viewVisible" title="资源详情" width="560px" append-to-body>
      <el-descriptions :column="1" border v-loading="viewing">
        <el-descriptions-item v-for="(v, k) in detail" :key="k" :label="k">
          {{ display(v) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, View, Box, Microphone, ChatDotSquare, MagicStick, Document, Lock, InfoFilled } from '@element-plus/icons-vue'
import { resourceList, resourceAdd, resourceGet, resourceUpdate, resourceDelete } from '@/api'
import { RES_FIELDS } from './resFields'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const props = defineProps({ resType: { type: String, required: true } })
const meta = computed(() => RES_FIELDS[props.resType])
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
    await ElMessageBox.confirm(`确认删除 ID=${row.id} 的${meta.value.label}？（软删除）`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await resourceDelete(props.resType, row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function openView(row) {
  viewVisible.value = true
  viewing.value = true
  detail.value = {}
  try {
    detail.value = await resourceGet(props.resType, row.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    viewing.value = false
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
</style>
