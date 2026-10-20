<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title" style="margin-bottom:0">
          <el-icon><ChatLineSquare /></el-icon>对话记录
          <span class="count-chip">{{ total }}</span>
        </div>
        <div class="toolbar-right">
          <el-select v-model="query.tenant_id" placeholder="全部租户" clearable filterable style="width: 180px" @change="reload">
            <el-option v-for="t in tenants" :key="t.id" :label="t.tenantname" :value="t.id" />
          </el-select>
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                          range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"
                          clearable style="width: 260px" @change="reload" />
          <el-button :icon="Refresh" round plain @click="reload">刷新</el-button>
        </div>
      </div>

      <el-table :data="rows" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="session_id" label="会话 ID" min-width="200">
          <template #default="{ row }">
            <span class="sid" :title="row.session_id">{{ row.session_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="tenantname" label="租户" width="140">
          <template #default="{ row }">
            <span class="tenant-name">{{ row.tenantname || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资源（LLM / ASR / TTS）" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="res-desc">{{ row.llm_desc || '?' }} / {{ row.asr_desc || '?' }} / {{ row.tts_desc || '?' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rounds" label="消息数" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.rounds > 0 ? 'primary' : 'info'" effect="plain" round>
              {{ row.rounds || 0 }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="开始时间" width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain type="primary" @click="openDetail(row)">
              <el-icon style="margin-right:3px"><View /></el-icon>聊天记录
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>暂无会话记录</p>
          </div>
        </template>
      </el-table>

      <div class="pager" v-if="total > 0">
        <el-pagination background layout="total, sizes, prev, pager, next"
                       :total="total" v-model:current-page="query.page" v-model:page-size="query.size"
                       :page-sizes="[10, 20, 50, 100]" @current-change="load" @size-change="reload" />
      </div>
    </div>

    <!-- 聊天记录详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="`会话 #${detail?.id ?? ''}`" size="560px" append-to-body>
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="1" border size="small" class="meta">
            <el-descriptions-item label="租户">{{ detail.tenantname || '—' }}</el-descriptions-item>
            <el-descriptions-item label="会话 ID">
              <span class="sid">{{ detail.session_id }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="资源">
              {{ detail.llm_desc || '?' }} / {{ detail.asr_desc || '?' }} / {{ detail.tts_desc || '?' }}
            </el-descriptions-item>
            <el-descriptions-item label="时间">
              {{ detail.create_time }} <span class="time-sep">→</span> {{ detail.update_time }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="chat" v-if="history.length">
            <div v-for="(m, i) in history" :key="i" class="msg-row" :class="m.role === 'user' ? 'right' : 'left'">
              <div class="bubble" :class="m.role === 'user' ? 'b-user' : 'b-bot'">
                <div class="role-tag">{{ m.role === 'user' ? '用户' : '数字人' }}</div>
                <div class="text">{{ m.content }}</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="该会话没有聊天记录（连接进行中或历史版本未记录）" :image-size="80" />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Box, ChatLineSquare, View } from '@element-plus/icons-vue'
import { sessionList, sessionGet, tenantList } from '@/api'

const route = useRoute()
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const tenants = ref([])
const dateRange = ref(null)

const query = reactive({
  tenant_id: route.query.tenant_id ? Number(route.query.tenant_id) : null,
  page: 1,
  size: 20
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

const history = computed(() => {
  const h = detail.value?.dialogue_history
  return Array.isArray(h) ? h : []
})

// 支持从租户列表「对话」按钮带 ?tenant_id= 跳入后切换路由参数
watch(() => route.query.tenant_id, (v) => {
  query.tenant_id = v ? Number(v) : null
  reload()
})

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.tenant_id != null) params.tenant_id = query.tenant_id
    if (dateRange.value && dateRange.value.length === 2) {
      params.start = dateRange.value[0]
      params.end = dateRange.value[1]
    }
    const data = await sessionList(params)
    rows.value = data.rows
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await sessionGet(row.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  try {
    tenants.value = await tenantList()
  } catch (e) { /* 下拉加载失败不阻塞列表 */ }
  await load()
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 10px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 10px; align-items: center; margin-left: auto; }
.card-title { display: flex; align-items: center; gap: 7px; font-size: 15px; font-weight: 650; color: #3b3f52; }
.card-title .el-icon { color: #6366f1; }
.count-chip {
  background: linear-gradient(135deg, #6366f1, #06b6d4); color: #fff;
  font-size: 11.5px; padding: 1px 9px; border-radius: 999px; font-weight: 600;
}
.mono { font-family: ui-monospace, "SF Mono", Consolas, monospace; color: #6366f1; }
.sid { font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 12px; color: #6b7186; word-break: break-all; }
.tenant-name { font-weight: 600; color: #23283b; }
.res-desc { font-size: 12.5px; color: #6b7186; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
.meta { margin-bottom: 18px; }
.time-sep { color: #b3bacc; margin: 0 4px; }

/* 聊天气泡 */
.chat { display: flex; flex-direction: column; gap: 12px; padding: 4px 2px; }
.msg-row { display: flex; }
.msg-row.right { justify-content: flex-end; }
.msg-row.left { justify-content: flex-start; }
.bubble { max-width: 82%; padding: 9px 12px; border-radius: 12px; font-size: 13.5px; line-height: 1.6; }
.b-user { background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; border-top-right-radius: 4px; }
.b-bot { background: #f1f3f9; color: #2c3145; border-top-left-radius: 4px; }
.role-tag { font-size: 11px; opacity: .72; margin-bottom: 3px; }
.text { white-space: pre-wrap; word-break: break-word; }
</style>
