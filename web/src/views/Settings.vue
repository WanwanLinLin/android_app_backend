<template>
  <div class="settings-page fade-up">
    <div class="page-head">
      <h1>设置</h1>
      <p class="muted">API Key 归属本账号、各模块开放接口共用。外部系统凭 Key 即可调用知识库检索、文档查询与上传解析等对外接口。</p>
    </div>

    <div class="section page-card">
      <div class="section-head">
        <div>
          <div class="section-title">API Key</div>
          <div class="muted">每个 Key 归属当前账号，可访问该账号有权的开放接口（当前为知识库）；明文密钥只在创建时显示一次，请妥善保管。</div>
        </div>
        <el-button type="primary" round @click="openAdd">
          <el-icon style="margin-right:4px"><Plus /></el-icon>生成 API Key
        </el-button>
      </div>

      <el-table :data="keys" v-loading="loading" style="width:100%"
                :header-cell-style="{ fontWeight: 600, background: '#fafbff' }">
        <el-table-column label="备注名" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name || '默认密钥' }}</template>
        </el-table-column>
        <el-table-column label="密钥" width="180">
          <template #default="{ row }">
            <span class="mono key-preview">{{ row.key_prefix }}••••••••••</span>
          </template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" label="归属" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.created_by === auth.id" size="small" type="success" effect="light" round>我的</el-tag>
            <span v-else class="muted">{{ row.owner_name || ('用户#' + row.created_by) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small" effect="light" round>
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近使用" width="170">
          <template #default="{ row }">{{ row.last_used_time || '从未使用' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ row.create_time || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="right" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" text :type="row.status === 1 ? 'warning' : 'success'"
                         :disabled="!canOperate(row)" @click="toggle(row)">
                {{ row.status === 1 ? '停用' : '启用' }}
              </el-button>
              <el-button size="small" text type="danger" :disabled="!canOperate(row)"
                         @click="onDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="34" color="#c0c6d9"><Key /></el-icon>
            <p>还没有 API Key，点击「生成 API Key」开始</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 使用说明 -->
    <div class="section page-card">
      <div class="section-head">
        <div>
          <div class="section-title">接口说明</div>
          <div class="muted">请求头携带 <span class="mono">Authorization: Bearer &lt;你的 API Key&gt;</span>，可访问且仅可访问本账号自建的知识库。</div>
        </div>
      </div>

      <div class="doc-block">
        <div class="doc-item" v-for="d in docs" :key="d.method + d.path">
          <div class="doc-line">
            <el-tag :type="d.method === 'GET' ? 'success' : 'primary'" size="small" effect="dark" round>
              {{ d.method }}
            </el-tag>
            <span class="mono doc-path">{{ baseOrigin }}{{ d.path }}</span>
          </div>
          <div class="muted doc-desc">{{ d.desc }}</div>
          <pre class="doc-curl">{{ d.curl }}</pre>
        </div>
      </div>
    </div>

    <!-- 生成结果弹窗 -->
    <el-dialog v-model="createdVisible" title="API Key 已生成" width="560px" :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon
                title="明文密钥仅此一次可见，关闭后无法再次查看，请立即复制保存。"
                style="margin-bottom:14px" />
      <div class="key-row">
        <el-input :model-value="createdKey" readonly class="mono" />
        <el-button type="primary" round @click="copy(createdKey)">复制</el-button>
      </div>
      <template #footer>
        <el-button round type="primary" @click="createdVisible = false">我已保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增对话框 -->
    <el-dialog v-model="addVisible" title="生成 API Key" width="460px" destroy-on-close>
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="备注名">
          <el-input v-model="newName" placeholder="如：产线质检系统（可选）" maxlength="64" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="addVisible = false">取消</el-button>
        <el-button type="primary" round :loading="creating" @click="doCreate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Key } from '@element-plus/icons-vue'
import { apiKeyList, apiKeyAdd, apiKeyStatus, apiKeyDelete } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
// 后端与本前端同源部署（生产 nginx 把 /v1 反代到后端），文档里的示例地址跟随当前 origin
const baseOrigin = location.origin

const keys = ref([])
const loading = ref(false)
// 仅本人可停/删自己的 key；admin 可见全部但只操作自己的（与后端口径一致）
const canOperate = (row) => row.created_by === auth.id

async function loadKeys() {
  loading.value = true
  try {
    const data = await apiKeyList()
    keys.value = data.rows || []
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

const addVisible = ref(false)
const creating = ref(false)
const newName = ref('')
function openAdd() { newName.value = ''; addVisible.value = true }
async function doCreate() {
  creating.value = true
  try {
    const data = await apiKeyAdd({ name: newName.value.trim() || null })
    addVisible.value = false
    createdKey.value = data.api_key
    createdVisible.value = true
    loadKeys()
  } catch (e) { ElMessage.error(e.message) } finally { creating.value = false }
}

const createdVisible = ref(false)
const createdKey = ref('')

async function toggle(row) {
  const next = row.status === 1 ? 0 : 1
  try {
    await apiKeyStatus(row.id, next)
    row.status = next
    ElMessage.success(next === 1 ? '已启用' : '已停用')
  } catch (e) { ElMessage.error(e.message) }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`删除 API Key「${row.name || '默认密钥'}」后，使用该 Key 的外部系统将立即失去访问权限。`,
      '确认删除', { type: 'warning', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    await apiKeyDelete(row.id)
    ElMessage.success('已删除')
    loadKeys()
  } catch (e) { ElMessage.error(e.message) }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('浏览器不允许自动复制，请手动选中复制')
  }
}

const docs = [
  {
    method: 'POST', path: '/v1/kb/open/retrieval', desc: '检索（混合 BM25+向量）。不传 kb_ids 则检索本账号全部知识库。',
    curl: `curl -X POST ${baseOrigin || 'http://<host:8852>'}/v1/kb/open/retrieval \\\n  -H "Authorization: Bearer <API_KEY>" \\\n  -H "Content-Type: application/json" \\\n  -d '{"question":"如何开机？","size":5,"kb_ids":[1]}'`,
  },
  {
    method: 'GET', path: '/v1/kb/open/kb/list', desc: '本账号可访问的知识库列表。',
    curl: `curl ${baseOrigin || 'http://<host:8852>'}/v1/kb/open/kb/list \\\n  -H "Authorization: Bearer <API_KEY>"`,
  },
  {
    method: 'GET', path: '/v1/kb/open/{kb_id}/document/list', desc: '指定知识库的文档列表（分页：page/size）。',
    curl: `curl "${baseOrigin || 'http://<host:8852>'}/v1/kb/open/1/document/list?page=1&size=20" \\\n  -H "Authorization: Bearer <API_KEY>"`,
  },
  {
    method: 'POST', path: '/v1/kb/open/{kb_id}/document/upload', desc: '上传文档（multipart，字段名 files，可多个；可选 ?parser_id= 指定切片方法）。',
    curl: `curl -X POST ${baseOrigin || 'http://<host:8852>'}/v1/kb/open/1/document/upload \\\n  -H "Authorization: Bearer <API_KEY>" \\\n  -F "files=@手册.pdf"`,
  },
]

onMounted(loadKeys)
</script>

<style scoped>
.page-head { margin-bottom: 20px; }
.page-head h1 { margin: 0; font-size: 24px; font-weight: 700; color: #1f2430; }
.page-head p { margin: 6px 0 0; font-size: 13px; }

.section { padding: 22px 24px; margin-bottom: 18px; }
.section-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 18px; flex-wrap: wrap;
}
.section-title { font-size: 16px; font-weight: 600; color: #23283b; margin-bottom: 4px; }

.mono { font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace; }
.key-preview { color: #6b7188; letter-spacing: 0.5px; }
.row-actions { display: flex; align-items: center; justify-content: flex-end; gap: 2px; white-space: nowrap; }
.row-actions :deep(.el-button + .el-button) { margin-left: 0; }

.doc-block { display: flex; flex-direction: column; gap: 18px; }
.doc-item { border: 1px solid #eef0f7; border-radius: 12px; padding: 14px 16px; background: #fbfbfe; }
.doc-line { display: flex; align-items: center; gap: 10px; }
.doc-path { font-size: 13px; color: #4338ca; word-break: break-all; }
.doc-desc { font-size: 12.5px; margin: 6px 0 10px; }
.doc-curl {
  margin: 0; background: #2c3142; color: #e6e8f0; border-radius: 8px;
  padding: 12px 14px; font-size: 12px; line-height: 1.6; overflow-x: auto;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
}

.empty { text-align: center; color: #9aa0b5; padding: 24px 0; }
.empty p { margin: 10px 0 0; font-size: 13px; }

.key-row { display: flex; gap: 10px; align-items: center; }
</style>
