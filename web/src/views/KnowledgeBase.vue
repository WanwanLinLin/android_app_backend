<template>
  <div class="kb-page fade-up">
    <!-- 顶部：欢迎语 + 搜索 + 创建（ragflow 风格） -->
    <div class="kb-header">
      <div class="kb-hello">
        <h1>欢迎回来，{{ auth.username || '朋友' }}</h1>
        <p>今天我们要使用哪个知识库？</p>
      </div>
      <div class="kb-header-actions">
        <el-input v-model="keyword" placeholder="搜索" clearable class="kb-search"
                  :prefix-icon="Search" @keyup.enter="loadKbs" @clear="loadKbs" />
        <el-button :icon="Refresh" circle plain title="刷新" @click="loadKbs" />
        <el-button type="primary" round @click="openAdd">
          <el-icon style="margin-right:4px"><Plus /></el-icon>创建知识库
        </el-button>
      </div>
    </div>

    <!-- 知识库卡片网格 -->
    <div class="kb-grid" v-loading="loading">
      <div v-for="kb in filteredKbs" :key="kb.id" class="kb-card" @click="openDetail(kb)">
        <div class="kb-card-top">
          <div class="kb-icon">
            <el-icon :size="20"><Notebook /></el-icon>
          </div>
          <el-dropdown trigger="click" placement="bottom-end" @command="(c) => onCardCommand(c, kb)"
                       @click.stop>
            <span class="kb-more" @click.stop><el-icon :size="18"><MoreFilled /></el-icon></span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="docs" :icon="Document">文档</el-dropdown-item>
                <el-dropdown-item command="test" :icon="Aim">检索测试</el-dropdown-item>
                <el-dropdown-item command="config" :icon="Setting">配置</el-dropdown-item>
                <el-dropdown-item command="delete" :icon="Delete" divided :disabled="!isMine(kb)"
                                  style="color:#dc2626">删除知识库</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="kb-card-name" :title="kb.name">{{ kb.name }}</div>
        <div class="kb-card-desc" :title="kb.desc">{{ kb.desc || '暂无描述' }}</div>

        <div class="kb-card-meta">
          <span><el-icon><Document /></el-icon>{{ kb.doc_num }} 文档</span>
          <span><el-icon><Clock /></el-icon>{{ fmtTime(kb.create_time) }}</span>
          <span v-if="kb.chunk_num" class="muted">{{ kb.chunk_num }} 切片 · {{ fmtTokens(kb.token_num) }} tokens</span>
        </div>

        <div class="kb-card-foot">
          <el-tag size="small" effect="plain" round class="embd-tag mono">{{ kb.embd_dim }}d</el-tag>
          <template v-if="auth.isAdmin">
            <el-tag v-if="isMine(kb)" size="small" type="success" effect="light" round>我的</el-tag>
            <span v-else class="muted owner-name">{{ kb.owner_name || ('用户#' + kb.created_by) }}</span>
          </template>
        </div>
      </div>

      <!-- 创建新卡片占位（对齐 ragflow 的「+」格子） -->
      <div class="kb-card kb-card-new" @click="openAdd">
        <el-icon :size="30"><Plus /></el-icon>
        <span>创建知识库</span>
      </div>

      <div v-if="!loading && !filteredKbs.length" class="kb-empty-tip">
        {{ keyword ? `没有匹配「${keyword}」的知识库` : '还没有知识库，点击右上角「创建知识库」开始' }}
      </div>
    </div>

    <!-- 新建知识库 -->
    <el-dialog v-model="formVisible" title="新建知识库"
               width="560px" destroy-on-close append-to-body>
      <el-form :model="form" label-width="130px" ref="formRef">
        <el-form-item label="名称" prop="name"
                      :rules="[{ required: true, message: '名称不能为空', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：产品售后知识库" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.desc" placeholder="简短描述（可选）" />
        </el-form-item>
        <el-form-item label="嵌入模型">
          <el-select v-model="form.embd_id" style="width: 100%">
            <el-option v-for="m in embdModels" :key="m.id" :value="m.id"
                       :label="`${m.id}（${m.dim} 维${m.default ? ' · 默认' : ''}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="切片方法">
          <el-select v-model="form.parser_id" style="width: 100%">
            <el-option v-for="p in parserMethods" :key="p.id" :value="p.id" :label="p.id">
              <span style="float:left">{{ p.id }}</span>
              <span class="muted" style="float:right;font-size:12px">{{ p.desc }}</span>
            </el-option>
          </el-select>
          <div class="muted" style="font-size:12px;margin-top:2px">上传文档可单独改，未指定的文档继承该默认值</div>
        </el-form-item>
        <el-form-item label="分块 Token 数">
          <el-input-number v-model="form.chunk_token_num" :min="64" :max="2048" :step="64" />
        </el-form-item>
        <el-form-item label="相似度阈值">
          <el-input-number v-model="form.similarity_threshold" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="向量权重">
          <el-input-number v-model="form.vector_similarity_weight" :min="0" :max="1" :step="0.05" :precision="2" />
          <span class="muted" style="margin-left:8px">其余权重给全文检索</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button round @click="formVisible = false">取消</el-button>
        <el-button type="primary" round :loading="saving" @click="saveKb">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Notebook, Plus, Refresh, Search, MoreFilled, Document, Clock, Aim, Setting, Delete
} from '@element-plus/icons-vue'
import { kbList, kbAdd, kbDelete, kbEmbeddingModels, kbParserMethods } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 知识库按创建者私有：删除仅本人（admin 也只看不动别人的库）
const isMine = (row) => !!row && row.created_by === auth.id

const kbs = ref([])
const loading = ref(false)
const embdModels = ref([])
const parserMethods = ref([])
const keyword = ref('')

const filteredKbs = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return kbs.value
  return kbs.value.filter(k =>
    (k.name || '').toLowerCase().includes(kw) || (k.desc || '').toLowerCase().includes(kw))
})

function openDetail(kb, tab) {
  router.push(tab ? `/kb/ragflow/${kb.id}?tab=${tab}` : `/kb/ragflow/${kb.id}`)
}

// 卡片右上角「···」菜单：跳转详情页对应标签
function onCardCommand(cmd, kb) {
  if (cmd === 'delete') onDeleteKb(kb)
  else openDetail(kb, cmd) // docs | test | config
}

function fmtTime(t) {
  if (!t) return '—'
  return String(t).slice(0, 16)
}
function fmtTokens(n) {
  if (!n) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + ' 万'
  return String(n)
}

async function loadKbs() {
  loading.value = true
  try {
    const data = await kbList()
    kbs.value = data.rows || []
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

onMounted(async () => {
  loadKbs()
  try {
    const [d, pm] = await Promise.all([kbEmbeddingModels(), kbParserMethods()])
    embdModels.value = d.models || []
    form.embd_id = d.default
    parserMethods.value = pm.methods || []
    form.parser_id = pm.default || 'General'
  } catch (e) { /* 模型/切片列表失败不阻断页面 */ }
})

// ---------------- 新建 ----------------
const formVisible = ref(false)
const saving = ref(false)
const form = reactive({ name: '', desc: '', embd_id: '', parser_id: 'General',
                        chunk_token_num: 256,
                        similarity_threshold: 0.2, vector_similarity_weight: 0.3 })

function openAdd() {
  Object.assign(form, { name: '', desc: '', parser_id: 'General', chunk_token_num: 256,
                        similarity_threshold: 0.2, vector_similarity_weight: 0.3 })
  formVisible.value = true
}
async function saveKb() {
  if (!form.name.trim()) return ElMessage.warning('名称不能为空')
  saving.value = true
  try {
    const d = await kbAdd({ ...form, name: form.name.trim() })
    formVisible.value = false
    ElMessage.success('已创建')
    // 新建后直接进详情页传文档，体验对齐 ragflow
    if (d?.id) router.push(`/kb/ragflow/${d.id}`)
    else loadKbs()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}
async function onDeleteKb(row) {
  try {
    await ElMessageBox.confirm(
      `删除知识库「${row.name}」将同时删除其 ${row.doc_num} 个文档及全部索引数据，不可恢复。`,
      '危险操作', { type: 'warning', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    await kbDelete(row.id)
    ElMessage.success('已删除')
    loadKbs()
  } catch (e) { ElMessage.error(e.message) }
}
</script>

<style scoped>
/* ============ 顶部欢迎区 ============ */
.kb-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16px; flex-wrap: wrap; margin-bottom: 22px;
}
.kb-hello h1 {
  margin: 0; font-size: 26px; font-weight: 700; letter-spacing: 0.5px; color: #1f2430;
}
.kb-hello p { margin: 6px 0 0; font-size: 13px; color: #8a90a6; }
.kb-header-actions { display: flex; align-items: center; gap: 10px; }
.kb-search { width: 240px; }
.kb-search :deep(.el-input__wrapper) { border-radius: 18px; }

/* ============ 卡片网格 ============ */
.kb-grid {
  display: grid; gap: 16px; min-height: 240px;
  grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
}
.kb-card {
  position: relative; background: #fff; border-radius: 14px; cursor: pointer;
  border: 1px solid rgba(99, 102, 241, 0.12); box-shadow: var(--dh-shadow-card);
  padding: 18px 18px 14px; display: flex; flex-direction: column;
  transition: transform 0.18s ease, box-shadow 0.25s ease, border-color 0.2s ease;
}
.kb-card:hover {
  transform: translateY(-3px); border-color: rgba(99, 102, 241, 0.4);
  box-shadow: var(--dh-shadow-float);
}
.kb-card-top { display: flex; align-items: flex-start; justify-content: space-between; }
.kb-icon {
  width: 42px; height: 42px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; color: #6366f1;
  background: linear-gradient(135deg, #eef1ff, #e6f7ff);
  border: 1px solid rgba(99, 102, 241, 0.18);
}
.kb-more {
  width: 28px; height: 28px; border-radius: 8px; display: flex;
  align-items: center; justify-content: center; color: #9aa0b5; outline: none;
  opacity: 0; transition: opacity 0.15s ease, background 0.15s ease;
}
.kb-card:hover .kb-more, .kb-more:focus { opacity: 1; }
.kb-more:hover { background: rgba(99, 102, 241, 0.1); color: #6366f1; }

.kb-card-name {
  margin-top: 18px; font-size: 17px; font-weight: 600; color: #23283b;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kb-card-desc {
  margin-top: 5px; font-size: 12.5px; color: #9aa0b5; min-height: 18px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kb-card-meta {
  margin-top: 16px; display: flex; flex-direction: column; gap: 5px;
  font-size: 12px; color: #6b7188;
}
.kb-card-meta span { display: flex; align-items: center; gap: 6px; }
.kb-card-meta .el-icon { color: #a5abc4; font-size: 13px; }

.kb-card-foot {
  margin-top: auto; padding-top: 12px; display: flex; align-items: center; gap: 8px;
}
.embd-tag { color: #6366f1; border-color: rgba(99, 102, 241, 0.3); }
.owner-name { font-size: 12px; }

/* 创建占位卡 */
.kb-card-new {
  align-items: center; justify-content: center; gap: 10px; min-height: 208px;
  color: #8f96b3; border: 1.5px dashed rgba(99, 102, 241, 0.35); background: transparent;
  box-shadow: none; font-size: 13.5px; flex-direction: column;
}
.kb-card-new:hover { color: #6366f1; border-color: #6366f1; background: rgba(99, 102, 241, 0.04); }
.kb-empty-tip {
  grid-column: 1 / -1; text-align: center; color: #9aa0b5;
  font-size: 13px; padding: 40px 0;
}
</style>
