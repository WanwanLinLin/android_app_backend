<template>
  <div class="tr-page fade-up">
    <!-- 顶部：返回 + 租户信息 -->
    <div class="hero">
      <el-button class="back-btn" round @click="router.back()">
        <el-icon style="margin-right:4px"><ArrowLeft /></el-icon>返回
      </el-button>
      <div class="hero-icon"><el-icon :size="26"><OfficeBuilding /></el-icon></div>
      <div class="hero-info">
        <div class="hero-name">{{ tenant?.tenantname || `租户 #${tenantId}` }}</div>
        <div class="hero-meta">
          <span v-if="tenant?.nickname">负责人：{{ tenant.nickname }}</span>
          <span v-if="tenant?.job">· {{ tenant.job }}</span>
          <span v-if="tenant?.phone_number">· {{ tenant.phone_number }}</span>
          <span v-if="tenant?.user_id">· 归属管理员：{{ adminName(tenant.user_id) }}</span>
        </div>
      </div>
      <el-button class="refresh-btn" round plain @click="refreshAll">
        <el-icon style="margin-right:4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- 类型统计卡（点击过滤） -->
    <div class="stat-row">
      <div v-for="t in TYPES" :key="t.value"
           class="stat-card" :class="{ active: filterType === t.value }"
           :style="{ '--accent': t.color }"
           @click="filterType = filterType === t.value ? '' : t.value">
        <div class="stat-ic"><el-icon :size="18"><component :is="t.icon" /></el-icon></div>
        <div>
          <div class="stat-num">{{ countOf(t.value) }}</div>
          <div class="stat-label">{{ t.label }}</div>
        </div>
        <div v-if="defaultOf(t.value)" class="stat-def" :title="`默认 #${defaultOf(t.value).reference_id}`">
          <el-icon><Star /></el-icon>
        </div>
      </div>
    </div>

    <!-- 当前默认资源 -->
    <div class="page-card default-card">
      <div class="card-title">
        <el-icon><Star /></el-icon>当前默认资源
        <span class="card-sub">终端不下发 source_config 时，会话即使用以下资源</span>
      </div>
      <div class="default-grid">
        <div v-for="t in TYPES" :key="t.value" class="default-item"
             :class="{ unset: !defaultOf(t.value) }" :style="{ '--accent': t.color }">
          <div class="default-head">
            <span class="type-chip" :style="{ '--accent': t.color }">
              <el-icon :size="13"><component :is="t.icon" /></el-icon>
              {{ t.label }}
            </span>
          </div>
          <div class="default-body">
            <template v-if="defaultOf(t.value)">
              <div class="default-main">
                {{ defaultSummary(t.value) }}
                <el-tag v-if="defaultOffShelf(t.value)" type="warning" size="small" effect="light">已下架</el-tag>
              </div>
              <div class="default-sub mono">#{{ defaultOf(t.value).reference_id }}</div>
            </template>
            <div v-else class="default-none">未设置默认</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 绑定操作区 -->
    <div class="page-card bind-card">
      <div class="card-title"><el-icon><Link /></el-icon>添加资源绑定</div>
      <div class="bind-bar">
        <el-select v-model="bindType" style="width: 150px">
          <el-option v-for="t in TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-select v-model="bindRefId" filterable placeholder="搜索并选择资源" style="flex: 1; min-width: 260px">
          <el-option v-for="opt in pool[bindType] || []" :key="opt.id"
                     :label="`#${opt.id} ${opt.desc || ''} (${opt.type || ''})`" :value="opt.id"
                     :disabled="opt.status === 'off_shelf'">
            <span :style="opt.status === 'off_shelf' ? 'color:#c0c6d9' : ''">
              {{ `#${opt.id} ${opt.desc || ''} (${opt.type || ''})` }}
              <el-tag v-if="opt.status === 'off_shelf'" type="warning" size="small" effect="light" style="margin-left:6px">已下架</el-tag>
            </span>
          </el-option>
        </el-select>
        <el-button type="primary" :loading="binding" @click="doBind">
          <el-icon style="margin-right:4px"><Plus /></el-icon>绑定
        </el-button>
      </div>
    </div>

    <!-- 已绑定资源表 -->
    <div class="page-card">
      <div class="card-title">
        <el-icon><Files /></el-icon>已绑定资源
        <el-tag v-if="filterType" size="small" closable type="info" style="margin-left:8px"
                @close="filterType = ''">{{ typeLabel(filterType) }} 过滤中</el-tag>
      </div>
      <el-table :data="filteredBound" v-loading="resLoading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <span class="type-chip" :style="{ '--accent': colorOf(row.type) }">
              <el-icon :size="13"><component :is="iconOf(row.type)" /></el-icon>
              {{ typeLabel(row.type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="reference_id" label="资源ID" width="90">
          <template #default="{ row }"><span class="mono">#{{ row.reference_id }}</span></template>
        </el-table-column>
        <el-table-column label="资源摘要" show-overflow-tooltip>
          <template #default="{ row }">
            {{ summary(row) }}
            <el-tooltip v-if="isOffShelf(row)" content="该资源已停止供给，建议更换绑定；现有会话仍可使用" placement="top">
              <el-tag type="warning" size="small" effect="light" style="margin-left:6px">已下架</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" effect="light" round size="small">
              <el-icon style="margin-right:2px"><Star /></el-icon>默认
            </el-tag>
            <span v-else class="dim">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain type="warning" :disabled="row.is_default"
                       @click="doSetDefault(row)">设为默认</el-button>
            <el-button size="small" round plain type="danger" @click="doUnbind(row)">解绑</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>该租户还没有绑定资源，从上方添加吧</p>
          </div>
        </template>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Refresh, OfficeBuilding, Microphone, ChatDotSquare,
  MagicStick, Document, Star, Link, Plus, Files, Box
} from '@element-plus/icons-vue'
import {
  tenantGet, tenantBindSource, tenantUnbindSource,
  tenantSourceList, tenantSetDefault, resourceList, userList
} from '@/api'

const route = useRoute()
const router = useRouter()
const tenantId = Number(route.params.id)

const TYPES = [
  { value: 'TTS', label: 'TTS 音色', color: '#6366f1', icon: Microphone },
  { value: 'ASR', label: 'ASR 识别', color: '#0ea5e9', icon: ChatDotSquare },
  { value: 'LLM', label: 'LLM 大模型', color: '#8b5cf6', icon: MagicStick },
  { value: 'CHATTEMPLATE', label: '对话模板', color: '#14b8a6', icon: Document }
]
const iconOf = (t) => (TYPES.find((x) => x.value === t) || {}).icon || Box
const colorOf = (t) => (TYPES.find((x) => x.value === t) || {}).color || '#909399'
const typeLabel = (t) => (TYPES.find((x) => x.value === t) || {}).label || t

const tenant = ref(null)
const admins = ref([])
const bound = ref([])
const resLoading = ref(false)
const filterType = ref('')
const bindType = ref('TTS')
const bindRefId = ref(null)
const binding = ref(false)
const pool = reactive({ TTS: [], ASR: [], LLM: [], CHATTEMPLATE: [] })

const filteredBound = computed(() =>
  filterType.value ? bound.value.filter((x) => x.type === filterType.value) : bound.value
)
const countOf = (t) => bound.value.filter((x) => x.type === t).length
const defaultOf = (t) => bound.value.find((x) => x.type === t && x.is_default)

async function ensurePool(type) {
  if (pool[type] && pool[type].length) return
  try {
    const data = await resourceList(type)
    pool[type] = data.rows || []
  } catch (e) { /* 资源池加载失败不阻塞页面 */ }
}

async function loadTenant() {
  try { tenant.value = await tenantGet(tenantId) }
  catch (e) { ElMessage.error(e.message) }
}

function adminName(id) {
  const u = admins.value.find((x) => x.id === id)
  return u ? (u.nickname ? `${u.username} · ${u.nickname}` : u.username) : `#${id}`
}

async function loadAdmins() {
  try { admins.value = await userList() }
  catch (e) { /* 管理员列表加载失败不阻塞页面 */ }
}

async function loadBound() {
  resLoading.value = true
  try {
    bound.value = await tenantSourceList(tenantId)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    resLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadTenant(), loadBound()])
}

function poolItem(row) {
  return (pool[row.type] || []).find((x) => x.id === row.reference_id)
}

// 已绑定资源的展示信息优先取后端随绑定一起返回的 desc/status（已下架资源
// 不在非 admin 的资源池列表里，不能靠 pool join）；pool 仅作兜底。
function isOffShelf(row) {
  if (row.status) return row.status === 'off_shelf'
  const opt = poolItem(row)
  return !!opt && opt.status === 'off_shelf'
}

function summary(row) {
  const opt = poolItem(row) || {}
  const desc = row.desc ?? opt.desc
  const extra = row.tag ?? opt.tag ?? row.voice ?? opt.voice ?? ''
  if (row.type === 'CHATTEMPLATE') {
    const mp = row.module_path ?? opt.module_path
    return `#${row.reference_id} ${[desc, mp].filter(Boolean).join(' ')}`.trim()
  }
  if (desc === undefined && !opt.desc) return `#${row.reference_id}`
  return `#${row.reference_id} ${[desc, extra].filter(Boolean).join(' ')}`.trim()
}

// 默认资源卡：主行放可读描述，资源 ID 单独一行（mono 样式），避免长文本挤压
function defaultSummary(type) {
  const d = defaultOf(type)
  if (!d) return ''
  const opt = (pool[type] || []).find((x) => x.id === d.reference_id) || {}
  if (type === 'CHATTEMPLATE') return d.desc || opt.desc || d.module_path || opt.module_path || '（无描述）'
  return d.desc || opt.desc || d.tag || opt.tag || d.voice || opt.voice || '（无描述）'
}

function defaultOffShelf(type) {
  const d = defaultOf(type)
  if (!d) return false
  if (d.status) return d.status === 'off_shelf'
  const opt = (pool[type] || []).find((x) => x.id === d.reference_id)
  return !!opt && opt.status === 'off_shelf'
}

async function doBind() {
  if (!bindRefId.value) { ElMessage.warning('请选择要绑定的资源'); return }
  binding.value = true
  try {
    await tenantBindSource(tenantId, { type: bindType.value, reference_id: bindRefId.value })
    ElMessage.success('绑定成功')
    bindRefId.value = null
    await loadBound()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    binding.value = false
  }
}

async function doUnbind(row) {
  try {
    await ElMessageBox.confirm(
      `确认解绑 ${typeLabel(row.type)} #${row.reference_id}？`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await tenantUnbindSource(tenantId, { type: row.type, reference_id: row.reference_id })
    ElMessage.success('已解绑')
    await loadBound()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function doSetDefault(row) {
  try {
    await tenantSetDefault(tenantId, { type: row.type, reference_id: row.reference_id })
    ElMessage.success(`已将 ${typeLabel(row.type)} 默认资源设为 #${row.reference_id}`)
    await loadBound()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await Promise.all([].concat(TYPES.map((t) => ensurePool(t.value)), [loadAdmins()]))
  await refreshAll()
})
</script>

<style scoped>
.tr-page { display: flex; flex-direction: column; gap: 16px; }

/* Hero */
.hero {
  display: flex; align-items: center; gap: 14px;
  background:
    radial-gradient(400px 120px at 85% 0%, rgba(6, 182, 212, 0.15), transparent 70%),
    linear-gradient(135deg, #ffffff, #f4f6ff);
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: 16px; padding: 16px 20px;
  box-shadow: var(--dh-shadow-card);
}
.back-btn { flex: none; }
.hero-icon {
  width: 52px; height: 52px; border-radius: 14px; flex: none;
  background: var(--dh-gradient); color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.3);
}
.hero-info { flex: 1; min-width: 0; }
.hero-name { font-size: 18px; font-weight: 700; color: #23283b; }
.hero-meta { font-size: 12.5px; color: #8a90a5; margin-top: 3px; }
.refresh-btn { flex: none; }

/* 统计卡 */
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.stat-card {
  position: relative; cursor: pointer;
  background: #fff; border: 1px solid rgba(99, 102, 241, 0.10);
  border-radius: 14px; padding: 14px 16px;
  display: flex; align-items: center; gap: 12px;
  box-shadow: var(--dh-shadow-card);
  transition: transform 0.18s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.stat-card:hover { transform: translateY(-3px); box-shadow: var(--dh-shadow-float); }
.stat-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), var(--dh-shadow-float); }
.stat-ic {
  width: 40px; height: 40px; border-radius: 12px; flex: none;
  background: color-mix(in srgb, var(--accent) 12%, white);
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
}
.stat-num { font-size: 22px; font-weight: 750; color: #23283b; line-height: 1.1; }
.stat-label { font-size: 12px; color: #8a90a5; margin-top: 2px; }
.stat-def {
  position: absolute; top: 10px; right: 12px;
  color: #f59e0b; font-size: 14px;
}

/* 卡片标题 */
.card-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 14.5px; font-weight: 650; color: #3b3f52; margin-bottom: 14px;
}
.card-title .el-icon { color: #6366f1; }
.card-sub { margin-left: 8px; font-size: 12px; font-weight: 400; color: #98a0b3; }

/* 当前默认资源 */
.default-card { border-left: 3px solid rgba(245, 158, 11, 0.55); }
.default-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.default-item {
  background: color-mix(in srgb, var(--accent) 5%, #fbfcff);
  border: 1px solid color-mix(in srgb, var(--accent) 16%, white);
  border-radius: 12px; padding: 12px 14px; min-width: 0;
}
.default-item.unset {
  background: #fafbfd; border-style: dashed;
  border-color: rgba(144, 147, 153, 0.35);
}
.default-head { margin-bottom: 8px; }
.default-body { min-height: 38px; }
.default-main {
  font-size: 13.5px; font-weight: 600; color: #23283b; line-height: 1.35;
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.default-sub { font-size: 11.5px; color: #8a90a5; margin-top: 4px; }
.default-none { font-size: 13px; color: #a8afc2; padding-top: 8px; }

.bind-card .bind-bar { display: flex; gap: 10px; align-items: center; }

.mono { font-family: ui-monospace, "SF Mono", Consolas, monospace; color: #6366f1; }
.type-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, white);
  border: 1px solid color-mix(in srgb, var(--accent) 28%, white);
}
.dim { color: #c0c6d9; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }

@media (max-width: 900px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .default-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
