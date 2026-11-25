<template>
  <div class="kb-detail fade-up" v-loading="kbLoading">
    <!-- 面包屑 -->
    <div class="crumb">
      <router-link to="/kb/ragflow">知识库</router-link>
      <span class="crumb-sep">/</span>
      <span class="crumb-cur">{{ kb?.name || '…' }}</span>
    </div>

    <div class="kb-body">
      <!-- 库内侧边栏（ragflow 风格） -->
      <aside class="kb-side">
        <div class="side-head">
          <div class="side-avatar"><el-icon :size="26"><Notebook /></el-icon></div>
          <div class="side-name" :title="kb?.name">{{ kb?.name || '…' }}</div>
        </div>
        <div class="side-divider"></div>
        <div class="side-menu">
          <div v-for="m in sideMenus" :key="m.key" class="side-item"
               :class="{ active: tab === m.key }" @click="tab = m.key">
            <el-icon><component :is="m.icon" /></el-icon><span>{{ m.label }}</span>
          </div>
        </div>
      </aside>

      <!-- 内容区 -->
      <section class="kb-main page-card">
        <!-- ========== 文档 ========== -->
        <template v-if="tab === 'docs'">
          <div class="main-title">文档</div>
          <div class="main-sub">😊 解析成功后才能问答哦。</div>

          <div class="doc-toolbar">
            <el-dropdown trigger="click" :disabled="!selection.length" @command="onBatch">
              <el-button round :disabled="!selection.length">
                批量<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="parse">批量解析</el-dropdown-item>
                  <el-dropdown-item command="delete" style="color:#dc2626">批量删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <div class="doc-toolbar-right">
              <el-input v-model="docKeyword" placeholder="搜索文件" clearable class="doc-search"
                        :prefix-icon="Search" />
              <el-dropdown trigger="click" :disabled="!canManage" @command="v => uploadParser = v">
                <el-button round plain :disabled="!canManage" title="本批次上传使用的切片方法">
                  <el-icon style="margin-right:4px"><Operation /></el-icon>切片：{{ uploadParser }}
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="p in parserMethods" :key="p.id" :command="p.id"
                                      :class="{ 'dp-active': p.id === uploadParser }">
                      <div class="dp-item">
                        <span>{{ p.id }}</span>
                        <small class="muted">{{ p.desc }}</small>
                      </div>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-upload :show-file-list="false" :http-request="doUpload" multiple
                         accept=".txt,.md,.pdf,.docx" :disabled="!canManage">
                <el-button type="primary" round :loading="uploading" :disabled="!canManage">
                  <el-icon style="margin-right:4px"><Plus /></el-icon>新增文件
                </el-button>
              </el-upload>
            </div>
          </div>

          <el-table :data="filteredDocs" v-loading="docsLoading" style="width:100%"
                    row-key="id" @selection-change="s => selection = s"
                    :header-cell-style="{ fontWeight: 600, background: '#fafbff' }">
            <el-table-column type="selection" width="42" :selectable="() => canManage" />
            <el-table-column label="名称" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="doc-name" @click="openChunks(row)">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="块数" width="90">
              <template #default="{ row }">
                <span class="doc-name" @click="openChunks(row)">{{ row.chunk_num }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上传日期" width="170">
              <template #default="{ row }">{{ fmtTime(row.create_time) }}</template>
            </el-table-column>
            <el-table-column label="切片方法" width="130">
              <template #default="{ row }">
                <el-dropdown trigger="click" :disabled="!canManage || row.run === 1"
                             @command="v => changeParser(row, v)">
                  <span class="parser-cell" :class="{ disabled: !canManage || row.run === 1 }">
                    {{ row.parser_id || 'General' }}
                    <el-icon v-if="canManage && row.run !== 1" :size="12"><ArrowDown /></el-icon>
                  </span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-for="p in parserMethods" :key="p.id" :command="p.id"
                                        :class="{ 'dp-active': p.id === row.parser_id }">
                        <div class="dp-item">
                          <span>{{ p.id }}</span>
                          <small class="muted">{{ p.desc }}</small>
                        </div>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="90">
              <template #default="{ row }">
                <el-switch v-model="row.available" :disabled="!canManage || switching.has(row.id)"
                           @change="v => toggleAvailable(row, v)" />
              </template>
            </el-table-column>
            <el-table-column label="解析状态" width="150" align="right">
              <template #default="{ row }">
                <el-tag v-if="row.run === 3" size="small" effect="light" class="st-ok" round>成功</el-tag>
                <el-tag v-else-if="row.run === -1" size="small" type="danger" effect="light" round
                        :title="row.progress_msg">失败</el-tag>
                <el-button v-else-if="row.run === 1" size="small" text class="st-run"
                           :title="row.progress_msg">解析中 {{ Math.round((row.progress || 0) * 100) }}%</el-button>
                <el-button v-else-if="canManage" size="small" text type="primary"
                           @click="reparse(row)">未解析·开始</el-button>
                <el-tag v-else size="small" type="info" effect="plain" round>未解析</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="right" fixed="right">
              <template #default="{ row }">
                <div class="row-actions">
                  <el-button v-if="canManage && (row.run === 3 || row.run === -1)" size="small" text
                             @click="reparse(row)">重解析</el-button>
                  <el-button v-if="canManage" size="small" text type="danger"
                             :disabled="row.run === 1" @click="onDeleteDoc(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
            <template #empty>
              <div class="empty">
                <el-icon :size="34" color="#c0c6d9"><Box /></el-icon>
                <p>{{ canManage ? '暂无文件，点击右上角「新增文件」上传' : '暂无文件' }}</p>
              </div>
            </template>
          </el-table>

          <div class="pager" v-if="docsTotal > docQuery.size">
            <el-pagination background layout="total, prev, pager, next, sizes" :total="docsTotal"
                           v-model:current-page="docQuery.page" v-model:page-size="docQuery.size"
                           :page-sizes="[10, 20, 50]" @current-change="loadDocs" @size-change="loadDocs" />
          </div>
        </template>

        <!-- ========== 检索测试 ========== -->
        <template v-else-if="tab === 'test'">
          <div class="main-title">检索测试</div>
          <div class="main-sub">验证该知识库的混合检索（BM25 全文 + 向量）效果。</div>

          <div class="ret-wrap">
            <div class="ret-config">
              <div class="ret-block-title">测试文本</div>
              <el-input v-model="retQuery.question" type="textarea" :rows="4"
                        placeholder="在此输入要检索的问题" @keyup.enter="doRetrieval" />
              <div class="ret-block-title" style="margin-top:18px">检索设置</div>
              <div class="ret-field">
                <span>相似度阈值</span>
                <el-slider v-model="retCfg.similarity_threshold" :min="0" :max="1"
                           :step="0.05" :format-tooltip="v => v.toFixed(2)" style="flex:1" />
                <b class="mono">{{ retCfg.similarity_threshold.toFixed(2) }}</b>
              </div>
              <div class="ret-field">
                <span>关键词权重</span>
                <el-slider v-model="retCfg.term_weight" :min="0" :max="1"
                           :step="0.05" :format-tooltip="v => v.toFixed(2)" style="flex:1" />
                <b class="mono">{{ retCfg.term_weight.toFixed(2) }}</b>
              </div>
              <div class="ret-field">
                <span>返回条数</span>
                <el-input-number v-model="retCfg.size" :min="1" :max="50" size="small" style="flex:1" />
              </div>
              <el-button type="primary" round style="width:100%;margin-top:16px"
                         :loading="reting" @click="doRetrieval">
                <el-icon style="margin-right:4px"><Search /></el-icon>搜索
              </el-button>
            </div>

            <div class="ret-result" v-loading="reting">
              <div v-if="retDone" class="ret-summary muted">
                命中 {{ retData.total }} 条 · 耗时 {{ retData.elapsed_ms }} ms
              </div>
              <div v-for="(c, i) in retData.chunks" :key="c.chunk_id" class="ret-item">
                <div class="ret-head">
                  <el-tag size="small" effect="dark" round>#{{ i + 1 }}</el-tag>
                  <span class="ret-doc mono">{{ c.document_name }}</span>
                  <span class="ret-score">综合 <b>{{ (c.similarity * 100).toFixed(1) }}%</b></span>
                  <span class="muted">向量 {{ (c.vector_similarity * 100).toFixed(1) }}%</span>
                </div>
                <div class="ret-content">{{ c.content }}</div>
                <div v-if="c.images && c.images.length" class="ret-images">
                  <el-image v-for="(u, k) in c.images" :key="k" :src="u" fit="cover"
                            class="ret-img" :preview-src-list="c.images" :initial-index="k"
                            preview-teleported lazy>
                    <template #error><div class="ret-img-err">图片加载失败</div></template>
                  </el-image>
                </div>
              </div>
              <el-empty v-if="retDone && !retData.chunks.length"
                        description="没有命中（可降低相似度阈值再试）" :image-size="80" />
              <el-empty v-else-if="!retDone" description="输入问题，点击「搜索」试试" :image-size="80" />
            </div>
          </div>
        </template>

        <!-- ========== 配置 ========== -->
        <template v-else-if="tab === 'config'">
          <div class="main-title">配置</div>
          <div class="main-sub">知识库解析与检索的默认参数，修改后立即生效（分块数只影响之后上传/重解析的文档）。</div>

          <el-form :model="cfg" label-width="140px" label-position="left" class="cfg-form">
            <el-form-item label="名称" required>
              <el-input v-model="cfg.name" :disabled="!canManage" maxlength="128" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="cfg.desc" :disabled="!canManage" maxlength="512" />
            </el-form-item>
            <el-form-item label="嵌入模型">
              <span class="mono">{{ kb?.embd_id }}</span>
              <el-tag size="small" effect="plain" round style="margin-left:8px">{{ kb?.embd_dim }} 维</el-tag>
              <span class="muted" style="margin-left:8px">建库后不可更改</span>
            </el-form-item>
            <el-form-item label="默认切片方法">
              <el-select v-model="cfg.parser_id" :disabled="!canManage" style="width:260px">
                <el-option v-for="p in parserMethods" :key="p.id" :value="p.id" :label="p.id">
                  <span style="float:left">{{ p.id }}</span>
                  <span class="muted" style="float:right;font-size:12px">{{ p.desc }}</span>
                </el-option>
              </el-select>
              <span class="muted" style="margin-left:12px">之后上传且未单独指定的文档使用该方式</span>
            </el-form-item>
            <el-form-item label="切片 Token 数量">
              <el-input-number v-model="cfg.chunk_token_num" :min="64" :max="2048" :step="64"
                               :disabled="!canManage" />
            </el-form-item>
            <el-form-item label="相似度阈值">
              <el-slider v-model="cfg.similarity_threshold" :min="0" :max="1" :step="0.05"
                         :disabled="!canManage" style="width:260px" />
            </el-form-item>
            <el-form-item label="命中候选数">
              <el-select v-model="cfg.rerank_limit" :disabled="!canManage" style="width:160px">
                <el-option v-for="n in [32, 48, 64]" :key="n" :value="n" :label="`${n} 条`" />
              </el-select>
              <span class="muted" style="margin-left:12px">参与融合/重排的候选上限（越大越全但越慢）</span>
            </el-form-item>
            <el-form-item label="PDF 整页转录">
              <el-select v-model="cfg.vision_page_ocr" :disabled="!canManage" style="width:200px">
                <el-option value="follow" label="跟随全局默认" />
                <el-option value="all" label="全文档逐页（表格手册最佳）" />
                <el-option value="scan" label="仅扫描件/图片页" />
                <el-option value="off" label="关闭" />
              </el-select>
              <span class="muted" style="margin-left:12px">视觉模型逐页转录，还原表格结构（仅 PDF 支持，需后台开启视觉）</span>
            </el-form-item>
            <el-form-item label="文档照片理解">
              <el-select v-model="cfg.vision_photo_describe" :disabled="!canManage" style="width:200px">
                <el-option value="follow" label="跟随全局默认" />
                <el-option value="on" label="开启（描述现场照片）" />
                <el-option value="off" label="关闭" />
              </el-select>
              <span class="muted" style="margin-left:12px">提取无文字照片的关键信息（病害、部位、标尺读数），并作为检索结果的配图</span>
              <div class="muted" style="font-size:12px;line-height:1.5">仅 PDF 和 DOCX 支持图像分析；TXT / Markdown 为纯文本，无图像分析</div>
            </el-form-item>
            <el-form-item label="关键词相似度权重">
              <el-slider v-model="cfg.term_weight" :min="0" :max="1" :step="0.05"
                         :disabled="!canManage" style="width:260px" />
              <span class="muted" style="margin-left:12px">其余权重给向量相似度</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" round :loading="savingCfg" :disabled="!canManage"
                         @click="saveConfig">保存配置</el-button>
              <span v-if="!canManage" class="muted">仅创建者可修改配置</span>
            </el-form-item>
          </el-form>

          <div class="cfg-danger" v-if="canManage">
            <div>
              <div class="cfg-danger-title">删除知识库</div>
              <div class="muted">删除后知识库、全部文档、索引与源文件均不可恢复。</div>
            </div>
            <el-button type="danger" round plain @click="onDeleteKb">
              <el-icon style="margin-right:4px"><Delete /></el-icon>删除知识库
            </el-button>
          </div>
        </template>
      </section>
    </div>

    <!-- chunk 查看 -->
    <el-dialog v-model="chunksVisible" :title="`切片内容 · ${curDoc?.name || ''}`"
               width="760px" append-to-body>
      <el-table :data="chunks" v-loading="chunksLoading" stripe max-height="440"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column label="#" width="60">
          <template #default="{ row }"><span class="mono">{{ row.position_int }}</span></template>
        </el-table-column>
        <el-table-column prop="content_with_weight" label="内容" show-overflow-tooltip />
        <el-table-column prop="token_num" label="Tokens" width="90" align="center" />
      </el-table>
      <div class="pager" v-if="chunksTotal > chunkQuery.size">
        <el-pagination background layout="total, prev, pager, next" :total="chunksTotal"
                       v-model:current-page="chunkQuery.page" :page-size="chunkQuery.size"
                       @current-change="loadChunks" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Notebook, Plus, Search, Box, Delete, ArrowDown, Document, Aim, Setting, Operation
} from '@element-plus/icons-vue'
import {
  kbGet, kbUpdate, kbDelete,
  kbDocList, kbDocUploadWithParser, kbDocParse, kbDocParser, kbDocAvailable, kbDocDelete,
  kbChunkList, kbRetrieval, kbParserMethods
} from '@/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const kbId = Number(route.params.kbId)

const sideMenus = [
  { key: 'docs', label: '文档', icon: Document },
  { key: 'test', label: '检索测试', icon: Aim },
  { key: 'config', label: '配置', icon: Setting },
]
const tab = ref(['docs', 'test', 'config'].includes(route.query.tab) ? route.query.tab : 'docs')

// ---------------- 知识库信息 ----------------
const kb = ref(null)
const kbLoading = ref(false)
const canManage = computed(() => !!kb.value && kb.value.created_by === auth.id)

async function loadKb() {
  kbLoading.value = true
  try {
    kb.value = await kbGet(kbId)
    if (kb.value?.parser_id) uploadParser.value = kb.value.parser_id
  } catch (e) {
    ElMessage.error(e.message || '知识库不存在或无权访问')
    router.replace('/kb/ragflow')
  } finally { kbLoading.value = false }
}

function fmtTime(t) { return t ? String(t).slice(0, 16) : '—' }

// ---------------- 文档 ----------------
const docs = ref([])
const docsTotal = ref(0)
const docsLoading = ref(false)
const uploading = ref(false)
const selection = ref([])
const docKeyword = ref('')
const switching = ref(new Set())
const docQuery = reactive({ page: 1, size: 10 })
const parserMethods = ref([])
const uploadParser = ref('General')   // 本批次上传使用的切片方法（默认继承库级）
let pollTimer = null

async function loadParserMethods() {
  try {
    const d = await kbParserMethods()
    parserMethods.value = d.methods || []
  } catch { /* 列表失败不阻断，单元格仍可显示行值 */ }
}

async function changeParser(row, pid) {
  if (pid === row.parser_id) return
  let alsoParse = false
  try {
    await ElMessageBox.confirm(
      `将「${row.name}」的切片方法改为 ${pid}？需重新解析后新分块方式才生效。`,
      '切换切片方法', { confirmButtonText: '修改并重解析', cancelButtonText: '仅修改', type: 'warning' })
    alsoParse = true
  } catch (act) {
    if (act !== 'cancel') return  // 点 X 关闭视为放弃
  }
  try {
    await kbDocParser(row.id, pid)
    row.parser_id = pid
    if (alsoParse) {
      await kbDocParse(row.id)
      ElMessage.success('已切换并重新提交解析')
      loadDocs()
    } else {
      ElMessage.success('已修改切片方法，重解析后生效')
    }
  } catch (e) { ElMessage.error(e.message) }
}

const filteredDocs = computed(() => {
  const kw = docKeyword.value.trim().toLowerCase()
  if (!kw) return docs.value
  return docs.value.filter(d => (d.name || '').toLowerCase().includes(kw))
})

async function loadDocs() {
  docsLoading.value = true
  try {
    const data = await kbDocList(kbId, { page: docQuery.page, size: docQuery.size })
    docs.value = data.rows || []
    docsTotal.value = data.total || 0
    schedulePoll()
  } catch (e) { ElMessage.error(e.message) } finally { docsLoading.value = false }
}

// 有排队/解析中的文档时 2s 轮询
function schedulePoll() {
  clearTimeout(pollTimer)
  if (docs.value.some(d => d.run === 1 || d.run === 0)) {
    pollTimer = setTimeout(loadDocsSilently, 2000)
  }
}
async function loadDocsSilently() {
  try {
    const data = await kbDocList(kbId, { page: docQuery.page, size: docQuery.size })
    docs.value = data.rows || []
    docsTotal.value = data.total || 0
    schedulePoll()
  } catch { /* 静默 */ }
}
onBeforeUnmount(() => clearTimeout(pollTimer))

async function doUpload(opt) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('files', opt.file)
    const r = await kbDocUploadWithParser(kbId, fd, uploadParser.value)
    if (r.failed?.length) ElMessage.warning(`${opt.file.name}：${r.failed[0]}`)
    else ElMessage.success(`${opt.file.name} 已提交解析`)
    loadDocs()
  } catch (e) { ElMessage.error(e.message) } finally { uploading.value = false }
}

async function reparse(row) {
  try {
    await kbDocParse(row.id)
    ElMessage.success('已提交解析')
    loadDocs()
  } catch (e) { ElMessage.error(e.message) }
}

async function toggleAvailable(row, v) {
  switching.value = new Set(switching.value).add(row.id)
  try {
    await kbDocAvailable(row.id, v)
    ElMessage.success(v ? '已启用，该文档重新参与检索' : '已停用，该文档不再参与检索')
  } catch (e) {
    row.available = !v
    ElMessage.error(e.message)
  } finally {
    const s = new Set(switching.value); s.delete(row.id); switching.value = s
  }
}

async function onDeleteDoc(row) {
  try {
    await ElMessageBox.confirm(`删除文档「${row.name}」及其全部索引切片？`, '确认', { type: 'warning' })
  } catch { return }
  try {
    await kbDocDelete(row.id)
    ElMessage.success('已删除')
    loadDocs()
  } catch (e) { ElMessage.error(e.message) }
}

async function onBatch(cmd) {
  const ids = selection.value.map(d => d.id)
  if (!ids.length) return
  if (cmd === 'parse') {
    try {
      await Promise.all(ids.map(id => kbDocParse(id)))
      ElMessage.success(`已提交 ${ids.length} 个文档解析`)
      loadDocs()
    } catch (e) { ElMessage.error(e.message) }
    return
  }
  try {
    await ElMessageBox.confirm(`批量删除 ${ids.length} 个文档及其全部索引切片？`, '危险操作',
      { type: 'warning', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    await Promise.all(ids.map(id => kbDocDelete(id)))
    ElMessage.success('已删除')
    loadDocs()
  } catch (e) { ElMessage.error(e.message) }
}

// ---------------- chunk 查看 ----------------
const chunksVisible = ref(false)
const curDoc = ref(null)
const chunks = ref([])
const chunksTotal = ref(0)
const chunksLoading = ref(false)
const chunkQuery = reactive({ page: 1, size: 10 })

function openChunks(row) {
  curDoc.value = row
  chunkQuery.page = 1
  chunksVisible.value = true
  loadChunks()
}
async function loadChunks() {
  chunksLoading.value = true
  try {
    const data = await kbChunkList(kbId,
      { doc_id: curDoc.value.id, page: chunkQuery.page, size: chunkQuery.size })
    chunks.value = data.rows || []
    chunksTotal.value = data.total || 0
  } catch (e) { ElMessage.error(e.message) } finally { chunksLoading.value = false }
}

// ---------------- 检索测试 ----------------
const reting = ref(false)
const retDone = ref(false)
const retData = reactive({ chunks: [], total: 0, elapsed_ms: 0 })
const retQuery = reactive({ question: '' })
const retCfg = reactive({ similarity_threshold: 0.2, term_weight: 0.7, size: 10 })

async function doRetrieval() {
  if (!retQuery.question.trim()) return ElMessage.warning('请输入检索问题')
  reting.value = true
  try {
    const d = await kbRetrieval({
      kb_ids: [kbId], question: retQuery.question, size: retCfg.size,
      similarity_threshold: retCfg.similarity_threshold,
      vector_similarity_weight: 1 - retCfg.term_weight })
    Object.assign(retData, { chunks: d.chunks || [], total: d.total || 0, elapsed_ms: d.elapsed_ms })
    retDone.value = true
  } catch (e) { ElMessage.error(e.message) } finally { reting.value = false }
}

// ---------------- 配置 ----------------
const savingCfg = ref(false)
const cfg = reactive({ name: '', desc: '', parser_id: 'General', chunk_token_num: 256,
                       similarity_threshold: 0.2, term_weight: 0.7, rerank_limit: 64,
                       vision_page_ocr: 'follow', vision_photo_describe: 'follow' })

watch(kb, (v) => {
  if (!v) return
  const vc = v.vision_config || {}
  Object.assign(cfg, {
    name: v.name, desc: v.desc || '', parser_id: v.parser_id || 'General',
    chunk_token_num: v.chunk_token_num,
    similarity_threshold: v.similarity_threshold,
    rerank_limit: [32, 48, 64].includes(v.rerank_limit) ? v.rerank_limit : 64,
    vision_page_ocr: vc.page_ocr || 'follow',
    vision_photo_describe: vc.photo_describe == null ? 'follow'
                          : (vc.photo_describe ? 'on' : 'off'),
    term_weight: Math.round((1 - (v.vector_similarity_weight ?? 0.3)) * 100) / 100 })
}, { immediate: true })

async function saveConfig() {
  if (!cfg.name.trim()) return ElMessage.warning('名称不能为空')
  savingCfg.value = true
  const vcfg = {}
  if (cfg.vision_page_ocr !== 'follow') vcfg.page_ocr = cfg.vision_page_ocr
  if (cfg.vision_photo_describe !== 'follow') vcfg.photo_describe = cfg.vision_photo_describe === 'on'
  try {
    await kbUpdate(kbId, {
      name: cfg.name.trim(), desc: cfg.desc, parser_id: cfg.parser_id,
      chunk_token_num: cfg.chunk_token_num,
      similarity_threshold: cfg.similarity_threshold,
      rerank_limit: cfg.rerank_limit,
      vision_config: vcfg,
      vector_similarity_weight: Math.round((1 - cfg.term_weight) * 100) / 100 })
    ElMessage.success('已保存')
    loadKb()
  } catch (e) { ElMessage.error(e.message) } finally { savingCfg.value = false }
}

async function onDeleteKb() {
  try {
    await ElMessageBox.confirm(
      `删除知识库「${kb.value.name}」将同时删除其 ${kb.value.doc_num} 个文档及全部索引数据，不可恢复。`,
      '危险操作', { type: 'warning', confirmButtonText: '确认删除',
                    confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    await kbDelete(kbId)
    ElMessage.success('已删除')
    router.replace('/kb/ragflow')
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => { loadKb(); loadDocs(); loadParserMethods() })
</script>

<style scoped>
/* 面包屑 */
.crumb { font-size: 13px; color: #8a90a6; margin-bottom: 14px; }
.crumb a { color: #8a90a6; text-decoration: none; }
.crumb a:hover { color: #6366f1; }
.crumb-sep { margin: 0 8px; color: #c3c8d9; }
.crumb-cur { color: #2c3142; font-weight: 600; }

.kb-body { display: flex; gap: 18px; align-items: stretch; min-height: 560px; }

/* 左侧库内菜单 */
.kb-side {
  width: 208px; flex: none; background: #fff; border-radius: 16px;
  border: 1px solid rgba(99, 102, 241, 0.08); box-shadow: var(--dh-shadow-card);
  padding: 26px 14px 18px; display: flex; flex-direction: column;
}
.side-head { text-align: center; padding: 0 6px; }
.side-avatar {
  width: 64px; height: 64px; margin: 0 auto; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; color: #6366f1;
  background: linear-gradient(135deg, #eef1ff, #e6f7ff);
  border: 1px solid rgba(99, 102, 241, 0.18);
}
.side-name {
  margin-top: 10px; font-size: 14.5px; font-weight: 600; color: #23283b;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.side-divider { border-top: 1.5px dashed #dfe3f0; margin: 18px 4px; }
.side-menu { display: flex; flex-direction: column; gap: 4px; }
.side-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  border-radius: 10px; font-size: 14px; color: #4b5165; cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.side-item:hover { background: #f3f4ff; color: #4f46e5; }
.side-item.active { background: #e8ebff; color: #4f46e5; font-weight: 600; }

/* 主区 */
.kb-main { flex: 1; min-width: 0; }
.main-title { font-size: 20px; font-weight: 700; color: #1f2430; }
.main-sub { font-size: 12.5px; color: #8a90a6; margin: 6px 0 20px; }

/* 文档工具栏 */
.doc-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.doc-toolbar-right { display: flex; align-items: center; gap: 10px; }
.doc-search { width: 230px; }
.doc-search :deep(.el-input__wrapper) { border-radius: 18px; }
.doc-name { color: #4f46e5; cursor: pointer; }
.doc-name:hover { text-decoration: underline; }
.st-ok { color: #4f46e5; background: #eef0ff; border-color: #dcdffc; }
.st-run { color: #d97706; }
/* 操作列：重解析 / 删除 同一行并排 */
.row-actions { display: flex; align-items: center; justify-content: flex-end; gap: 2px; white-space: nowrap; }
.row-actions :deep(.el-button + .el-button) { margin-left: 0; }

/* 检索测试 */
.ret-wrap { display: flex; gap: 18px; align-items: flex-start; }
.ret-config {
  width: 300px; flex: none; border: 1px solid #eef0f7; border-radius: 12px;
  padding: 16px; background: #fbfbfe;
}
.ret-block-title { font-size: 13px; font-weight: 600; color: #3b3f52; margin-bottom: 10px; }
.ret-field { display: flex; align-items: center; gap: 12px; font-size: 13px; color: #4b5165; margin-top: 8px; }
.ret-field b { width: 34px; text-align: right; color: #4f46e5; }
.ret-result { flex: 1; min-width: 0; min-height: 300px; }
.ret-summary { margin-bottom: 10px; font-size: 12.5px; }
.ret-item {
  border: 1px solid rgba(99, 102, 241, 0.14); border-radius: 10px;
  padding: 10px 12px; margin-bottom: 10px; background: rgba(99, 102, 241, 0.03);
}
.ret-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 12.5px; }
.ret-doc { color: #4338ca; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ret-score b { color: #16a34a; }
.ret-content {
  font-size: 13px; color: #3c4257; line-height: 1.65; max-height: 88px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
}
.ret-images { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.ret-img {
  width: 96px; height: 96px; border-radius: 8px; border: 1px solid #e4e7ec;
  cursor: zoom-in; background: #f6f7fb;
}
.ret-img-err {
  width: 96px; height: 96px; display: flex; align-items: center; justify-content: center;
  font-size: 12px; color: #98a2b3; background: #f6f7fb; border-radius: 8px;
}

/* 切片方法单元格（ragflow 风格：可点文字 + 小箭头） */
.parser-cell {
  display: inline-flex; align-items: center; gap: 4px; color: #4f46e5;
  cursor: pointer; outline: none; border-radius: 6px; padding: 2px 6px;
}
.parser-cell:hover { background: #f3f4ff; }
.parser-cell.disabled { color: #4b5165; cursor: default; }
.parser-cell.disabled:hover { background: transparent; }
.outline { outline: none; }

/* 配置 */
.cfg-form { max-width: 560px; margin-top: 4px; }
.cfg-danger {
  margin-top: 34px; padding-top: 18px; border-top: 1px solid #f0eefc;
  display: flex; align-items: center; justify-content: space-between; gap: 18px; max-width: 640px;
}
.cfg-danger-title { font-weight: 600; color: #b91c1c; margin-bottom: 4px; }
</style>

<style>
/* 切片方法下拉菜单项（el-dropdown 面板 teleport 到 body，需全局样式） */
.el-dropdown-menu__item.dp-active { color: #4f46e5; font-weight: 600; background: #f3f4ff; }
.el-dropdown-menu__item .dp-item { display: flex; flex-direction: column; line-height: 1.35; padding: 2px 0; }
.el-dropdown-menu__item .dp-item small { max-width: 300px; white-space: normal; }
</style>
