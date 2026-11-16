<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title">
          <el-icon><MagicStick /></el-icon>LLM自动化测试
          <span class="count-chip">{{ total }}</span>
        </div>
        <div class="toolbar-right">
          <el-button type="warning" round plain :loading="batchRunning"
                     :disabled="!rows.length" @click="onRunAll">
            <el-icon v-if="!batchRunning" style="margin-right:4px"><VideoPlay /></el-icon>
            {{ batchRunning ? `一键测试中 ${batch.done}/${batch.total}` : '一键测试' }}
          </el-button>
          <el-button :icon="Refresh" round plain @click="load">刷新</el-button>
          <el-button type="primary" round @click="openAdd">
            <el-icon style="margin-right:4px"><Plus /></el-icon>新建测试任务
          </el-button>
        </div>
      </div>
      <div v-if="batchRunning || batchFinishedTip" class="tip-bar" style="border-left-color:#e6a23c">
        <el-icon><Loading v-if="batchRunning" /><InfoFilled v-else /></el-icon>
        <template v-if="batchRunning">
          一键测试进行中：已完成 {{ batch.done }}/{{ batch.total }}
          <span v-if="batch.current_list.length" style="margin-left:8px">
            （{{ batch.current_list.length }} 个正在运行：{{ batch.current_list.join('、') }}）</span>
          <span v-if="batchWaiting > 0" style="margin-left:8px">（{{ batchWaiting }} 个排队中）</span>
          <span style="margin-left:8px">—— 最多 {{ batch.concurrency || 5 }} 个并发，结果实时写回下方列表</span>
        </template>
        <template v-else>{{ batchFinishedTip }}</template>
      </div>
      <div class="tip-bar">
        <el-icon><InfoFilled /></el-icon>
        对选定的 LLM 个性插件批量真实调用：每个插件在同一会话里按序多轮提问（最多 10 轮），
        并按自定义规则校验全部对话内容（包含 / 不包含 / 正则 / AI 判定——由后台配置的判定模型
        评审整个对话）；定时任务每天自动运行；结果可导出 PDF 报告。
      </div>

      <el-table :data="rows" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="64">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="任务名称" min-width="180">
          <template #default="{ row }">
            <div class="name-main" :title="row.desc || row.name">{{ row.name }}</div>
            <div v-if="row.desc" class="name-desc" :title="row.desc">{{ row.desc }}</div>
          </template>
        </el-table-column>
        <el-table-column label="测试插件" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="pid in (row.plugin_ids || []).slice(0, 3)" :key="pid" size="small"
                    effect="plain" class="plug-tag">{{ pluginName(pid) }}</el-tag>
            <span v-if="(row.plugin_ids || []).length > 3" class="muted">
              等 {{ row.plugin_ids.length }} 个</span>
          </template>
        </el-table-column>
        <el-table-column label="规则" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.rules || []).length" size="small" type="warning" effect="light">
              {{ row.rules.length }} 条</el-tag>
            <span v-else class="muted">仅联通</span>
          </template>
        </el-table-column>
        <el-table-column label="定时" width="150">
          <template #default="{ row }">
            <template v-if="row.schedule_enabled && row.schedule_status === 'pending'">
              <el-tag size="small" type="primary" effect="light">每天 {{ (row.schedule_time || '').slice(11, 16) }}</el-tag>
            </template>
            <el-tag v-else-if="row.schedule_status === 'running'" size="small" type="warning" effect="light">运行中</el-tag>
            <el-tag v-else-if="row.schedule_enabled" size="small" type="info" effect="light">已暂停</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="最近结果" width="170">
          <template #default="{ row }">
            <template v-if="row.last_summary">
              <span :class="row.last_summary.fail ? 'res-bad' : 'res-ok'">
                {{ row.last_summary.ok }}/{{ row.last_summary.total }} 通过</span>
              <div class="sub-time">{{ row.last_run_time }} ·
                {{ row.last_trigger === 'scheduled' ? '定时' : '手动' }}</div>
            </template>
            <span v-else class="muted">未运行</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="420" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button size="small" round type="primary" :loading="running === row.id"
                         :disabled="!canRun(row)" @click="onRun(row)">
                {{ running === row.id ? '运行中…' : '立即测试' }}
              </el-button>
              <el-button size="small" round plain :disabled="!row.last_summary" @click="openReport(row)">结果</el-button>
              <el-button size="small" round plain @click="openHistory(row)">历史</el-button>
              <el-button size="small" round plain :disabled="!row.last_summary" @click="onDownloadPdf(row)">PDF</el-button>
              <el-button size="small" round plain :disabled="!canEdit(row)" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" round plain type="danger" :disabled="!canEdit(row)" @click="onDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>暂无测试任务，点击右上角新建一个吧</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 新建 / 编辑任务 -->
    <el-dialog v-model="formVisible" :title="editingId ? '编辑测试任务' : '新建测试任务'"
               width="720px" destroy-on-close append-to-body>
      <el-form :model="form" label-width="110px" ref="formRef">
        <el-form-item label="任务名称" prop="name"
                      :rules="[{ required: true, message: '名称不能为空', trigger: 'blur' }]">
          <el-input v-model="form.name" placeholder="如：港中大数字人例行巡检" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.desc" placeholder="简短描述（可选）" />
        </el-form-item>
        <el-form-item label="测试插件" prop="plugin_ids"
                      :rules="[{ required: true, message: '至少选择一个 LLM 个性插件', trigger: 'change' }]">
          <el-select v-model="form.plugin_ids" multiple filterable style="width: 100%"
                     placeholder="可多选，逐个真实调用">
            <el-option v-for="p in llmPlugins" :key="p.id" :value="p.id"
                       :label="`#${p.id} ${p.name}（${p.base_plugin_name}）`" />
          </el-select>
          <div class="field-hint">选项为你可见的 LLM 个性插件；已选 {{ form.plugin_ids.length }} 个</div>
        </el-form-item>
        <el-form-item label="测试问题">
          <div style="width: 100%">
            <div v-for="(p, i) in form.test_prompts" :key="i" class="rule-row">
              <span class="turn-chip">第{{ i + 1 }}轮</span>
              <el-input v-model="form.test_prompts[i]" style="flex: 1"
                        :placeholder="i === 0 ? '第一句话，留空则默认：你好，请用一句话介绍你自己' : '接着上一轮继续问'" />
              <el-button :icon="Delete" circle plain type="danger" size="small"
                         @click="form.test_prompts.splice(i, 1)" />
            </div>
            <el-button size="small" round plain :icon="Plus"
                       :disabled="form.test_prompts.length >= 10"
                       @click="form.test_prompts.push('')">
              添加一轮（{{ form.test_prompts.length }}/10）
            </el-button>
            <div class="field-hint">
              多个问题在同一会话里按顺序逐轮提问（连续对话，工作流能记住上下文）；
              全部留空则使用默认问题。校验规则针对整个对话的回复内容生效。
            </div>
          </div>
        </el-form-item>

        <el-form-item label="结果校验规则">
          <div style="width: 100%">
            <div v-for="(r, i) in form.rules" :key="i" class="rule-row">
              <el-select v-model="r.type" style="width: 130px">
                <el-option value="contains" label="包含" />
                <el-option value="not_contains" label="不包含" />
                <el-option value="regex" label="正则匹配" />
                <el-option value="llm_judge" label="AI 判定" />
              </el-select>
              <el-input v-model="r.value" style="flex: 1"
                        :placeholder="r.type === 'llm_judge'
                          ? '用自然语言描述判定要求，如：回答必须是中文且为自我介绍'
                          : '填写片段或正则，如：助手'" />
              <el-button :icon="Delete" circle plain type="danger" size="small"
                         @click="form.rules.splice(i, 1)" />
            </div>
            <el-button size="small" round plain :icon="Plus" @click="form.rules.push({ type: 'contains', value: '' })">
              添加规则
            </el-button>
            <div class="field-hint">
              不添加规则 = 只测联通性（能返回非空输出即通过）；规则针对全部轮次的对话内容校验；
              AI 判定由后台配置的判定模型按你的描述评审整个对话记录，适合无法用关键字表达的要求。
            </div>
          </div>
        </el-form-item>

        <el-form-item label="定时运行">
          <el-switch v-model="form.schedule_enabled" />
          <el-time-picker v-if="form.schedule_enabled" v-model="form.daily_time"
                          value-format="HH:mm:ss" placeholder="每天运行时刻"
                          style="margin-left: 12px; width: 160px" />
          <div class="field-hint" style="width: 100%">
            每天重复任务：每天到该时刻后台自动运行一次，首次运行为最近的一个该时刻。{{ editingScheduleTip }}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 测试结果 -->
    <el-dialog v-model="reportVisible" title="测试结果" width="860px" append-to-body
               top="5vh">
      <div v-loading="reportLoading">
        <div v-if="report" class="report-head">
          <span class="mono">任务 #{{ report.task_id }} {{ report.task_name }}</span>
          <el-divider direction="vertical" />
          运行 {{ report.run_time }} · {{ report.trigger === 'scheduled' ? '定时' : '手动' }}
          <el-divider direction="vertical" />
          <span :class="report.summary.fail ? 'res-bad' : 'res-ok'" style="font-weight: 600">
            {{ report.summary.ok }}/{{ report.summary.total }} 通过</span>
          <el-button size="small" round plain style="margin-left: 10px"
                     @click="onExportReportPdf">导出 PDF</el-button>
        </div>
        <div v-if="report" class="tip-bar" style="margin-top: 10px">
          <el-icon><InfoFilled /></el-icon>
          测试问题（{{ (report.prompts || []).length }} 轮连续对话）：
          <span v-for="(p, i) in (report.prompts || [])" :key="i" class="prompt-item">
            第{{ i + 1 }}轮「{{ p }}」</span>
        </div>
        <el-collapse v-if="report" v-model="expanded" style="margin-top: 10px">
          <el-collapse-item v-for="it in report.items" :key="it.plugin_id" :name="it.plugin_id">
            <template #title>
              <el-tag :type="it.ok ? 'success' : 'danger'" size="small" effect="dark" style="margin-right: 8px">
                {{ it.ok ? '通过' : '失败' }}</el-tag>
              <span class="mono">#{{ it.plugin_id }}</span>
              <span style="margin-left: 6px">{{ it.plugin_name }}</span>
              <span class="muted" style="margin-left: auto; font-size: 12px">
                {{ (it.turns || []).length ? `${it.turns.length}轮 · ` : '' }}
                {{ it.seconds != null ? `耗时 ${it.seconds}s` : '' }}
                {{ it.first_token_seconds ? ` · 首token ${it.first_token_seconds}s` : '' }}</span>
            </template>
            <div v-if="it.error" class="err-line">错误：{{ it.error }}</div>
            <div v-if="(it.turns || []).length">
              <div class="sec-label">对话记录</div>
              <div v-for="t in it.turns" :key="t.index" class="turn-block">
                <div class="turn-q">第{{ t.index }}轮 问：{{ t.prompt }}</div>
                <pre v-if="t.output" class="content-pre">{{ t.output }}</pre>
                <div v-else-if="t.error" class="err-line" style="margin: 2px 0 0">
                  答：（失败：{{ t.error }}）</div>
              </div>
            </div>
            <div v-else-if="it.output">
              <div class="sec-label">模型输出</div>
              <pre class="content-pre">{{ it.output }}</pre>
            </div>
            <div v-if="(it.checks || []).length">
              <div class="sec-label">规则校验</div>
              <el-table :data="it.checks" size="small" style="width: 100%">
                <el-table-column label="规则" min-width="200">
                  <template #default="{ row }">
                    {{ ruleLabel(row.type) }}：{{ row.value }}</template>
                </el-table-column>
                <el-table-column label="结果" width="90">
                  <template #default="{ row }">
                    <span :class="row.passed ? 'res-ok' : 'res-bad'">
                      {{ row.passed ? '通过' : '未通过' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row }">
                    <div class="detail-text">{{ row.detail }}</div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button type="primary" @click="reportVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 历史测试记录 -->
    <el-dialog v-model="historyVisible" title="历史测试记录" width="860px" append-to-body top="6vh">
      <div v-loading="historyLoading">
        <div class="report-head" style="margin-bottom: 10px">
          <span class="mono">任务 #{{ historyTask?.id }} {{ historyTask?.name }}</span>
          <el-divider direction="vertical" />
          共 {{ historyTotal }} 次运行
        </div>
        <el-table :data="historyRows" stripe style="width: 100%"
                  :header-cell-style="{ fontWeight: 600 }">
          <el-table-column prop="run_time" label="运行时间" width="180" />
          <el-table-column label="触发方式" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="row.trigger === 'scheduled' ? 'primary' : 'info'" effect="light">
                {{ row.trigger === 'scheduled' ? '定时' : '手动' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="结果" width="140">
            <template #default="{ row }">
              <span v-if="row.summary" :class="row.summary.fail ? 'res-bad' : 'res-ok'" style="font-weight: 600">
                {{ row.summary.ok }}/{{ row.summary.total }} 通过</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" round plain @click="viewRunReport(row)">查看结果</el-button>
              <el-button size="small" round plain @click="onDownloadRunPdf(row)">PDF</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <div class="empty"><el-icon :size="36" color="#c0c6d9"><Box /></el-icon><p>该任务暂无历史运行记录</p></div>
          </template>
        </el-table>
        <div v-if="historyTotal > historySize" class="pager">
          <el-pagination background layout="prev, pager, next" :total="historyTotal"
                         :page-size="historySize" :current-page="historyPage"
                         @current-change="onHistoryPage" />
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="historyVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Delete, Box, MagicStick, InfoFilled, VideoPlay, Loading } from '@element-plus/icons-vue'
import { customPluginList, llmTestTaskList, llmTestTaskGet, llmTestTaskAdd,
         llmTestTaskUpdate, llmTestTaskDelete, llmTestTaskRun, llmTestReportPdf,
         llmTestTaskRuns, llmTestRunGet, llmTestRunPdf,
         llmTestRunAll, llmTestRunAllStatus } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const running = ref(null)
const llmPlugins = ref([])

const pluginName = (pid) => {
  const p = llmPlugins.value.find((x) => x.id === pid)
  return p ? p.name : `#${pid}`
}
// 严格私有：运行/改/删仅创建者本人（后端同口径兜底）
const canEdit = (row) => row.owner_id === auth.id
const canRun = (row) => canEdit(row) || auth.isAdmin
const ruleLabel = (t) => ({ contains: '包含', not_contains: '不包含',
                            regex: '正则匹配', llm_judge: 'AI 判定' }[t] || t)

async function load() {
  loading.value = true
  try {
    const [pl, tasks] = await Promise.all([customPluginList('LLM'), llmTestTaskList()])
    llmPlugins.value = pl.rows || []
    rows.value = tasks.rows || []
    total.value = tasks.total || rows.value.length
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  // 页面打开时若有一键测试批次在跑（如刷新过页面），恢复进度展示与轮询
  try {
    const s = await llmTestRunAllStatus()
    if (s.running) { applyBatchStatus(s); startBatchPolling() }
  } catch (e) { /* 忽略 */ }
})
onBeforeUnmount(stopBatchPolling)

// ===================== 新建 / 编辑 =====================
const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editingId = ref(null)
const editingStatus = ref(null)
const form = reactive({ name: '', desc: '', plugin_ids: [], test_prompts: [''],
                        rules: [], schedule_enabled: false, daily_time: null })
const editingScheduleTip = computed(() => editingId.value
  ? (editingStatus.value === 'running' ? '该任务正在定时运行中，稍后再改。' : '') : '保存后每天到点自动执行。')

function openAdd() {
  editingId.value = null
  editingStatus.value = null
  Object.assign(form, { name: '', desc: '', plugin_ids: [], test_prompts: [''],
                        rules: [], schedule_enabled: false, daily_time: null })
  formVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  editingStatus.value = row.schedule_status
  const prompts = (row.test_prompts || []).length ? [...row.test_prompts] : ['']
  Object.assign(form, {
    name: row.name, desc: row.desc || '', plugin_ids: [...(row.plugin_ids || [])],
    test_prompts: prompts, rules: (row.rules || []).map((r) => ({ ...r })),
    schedule_enabled: !!row.schedule_enabled,
    daily_time: row.schedule_time ? row.schedule_time.slice(11, 19) : null })
  formVisible.value = true
}

// 由「每天 HH:mm:ss」算首次运行时间：今天该时刻未过用今天，否则明天
function firstDailyTime(hms) {
  const today = new Date()
  const [h, m, s] = hms.split(':').map(Number)
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate(), h, m, s)
  if (t.getTime() <= Date.now() + 30000) t.setDate(t.getDate() + 1)
  const p = (n) => String(n).padStart(2, '0')
  return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())} ${p(h)}:${p(m)}:${p(s)}`
}

async function submitForm() {
  await formRef.value.validate().catch(() => { throw new Error('请检查必填项') })
  const rules = form.rules.filter((r) => str(r.value).trim())
  if (form.rules.length !== rules.length) { ElMessage.error('存在空的规则内容，请填写或删除'); return }
  const prompts = form.test_prompts.map((p) => str(p).trim()).filter(Boolean)
  if (prompts.length > 10) { ElMessage.error('测试问题最多 10 个'); return }
  if (form.schedule_enabled && !form.daily_time) { ElMessage.error('请选择每天运行时刻'); return }
  const payload = {
    name: form.name, desc: form.desc || null, plugin_ids: form.plugin_ids,
    test_prompts: prompts, rules,
    schedule_enabled: form.schedule_enabled,
    schedule_time: form.schedule_enabled ? firstDailyTime(form.daily_time) : null }
  submitting.value = true
  try {
    if (editingId.value) {
      await llmTestTaskUpdate(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await llmTestTaskAdd(payload)
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
function str(v) { return v == null ? '' : String(v) }

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除测试任务「${row.name}」？`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await llmTestTaskDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ===================== 立即运行 / 结果 =====================
const runningBusy = ref(false)

async function onRun(row) {
  if (runningBusy.value) return
  runningBusy.value = true
  running.value = row.id
  const msg = ElMessage({ message: `任务「${row.name}」运行中，插件较多时可能需要几分钟…`,
                          type: 'info', duration: 0 })
  try {
    const report = await llmTestTaskRun(row.id)
    showReport(report)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    msg.close()
    runningBusy.value = false
    running.value = null
  }
}

// ===================== 一键测试（后台运行，最多 5 个并发，其余排队） =====================
const batch = reactive({ running: false, total: 0, done: 0, ok: 0, fail: 0,
                         skipped: 0, current: null, current_list: [],
                         concurrency: 5 })
const batchRunning = computed(() => batch.running)
// 排队数 = 总数 - 已完成 - 正在运行（skipped 也已计入 done，不重复扣）
const batchWaiting = computed(() =>
  Math.max(batch.total - batch.done - (batch.current_list || []).length, 0))
const batchFinishedTip = ref('')
let batchTimer = null

function applyBatchStatus(s) {
  Object.assign(batch, s || {})
  if (!Array.isArray(batch.current_list)) batch.current_list = []
}

// 每次状态轮询顺带刷新列表，「最近结果」列实时亮起来
async function pollBatch() {
  try {
    const s = await llmTestRunAllStatus()
    applyBatchStatus(s)
    await load()
    if (!s.running) {
      stopBatchPolling()
      ElMessage.success(`一键测试完成：${s.ok} 个任务全部通过、${s.fail} 个有失败`
        + (s.skipped ? `，${s.skipped} 个运行中已跳过` : ''))
    }
  } catch (e) { /* 瞬断下一次再轮 */ }
}

function startBatchPolling() {
  stopBatchPolling()
  batchTimer = setInterval(pollBatch, 5000)
}

function stopBatchPolling() {
  if (batchTimer) { clearInterval(batchTimer); batchTimer = null }
}

async function onRunAll() {
  try {
    await ElMessageBox.confirm(
      `将把当前 ${rows.value.length} 个测试任务全部后台运行（最多 ${batch.concurrency || 5} 个并发，`
      + '其余排队；真实调用大模型，插件较多时整体可能需要几分钟）。'
      + '正在运行中的任务会自动跳过。', '一键开始测试', { type: 'warning', confirmButtonText: '开始测试' })
  } catch (e) { return }
  batchFinishedTip.value = ''
  try {
    const data = await llmTestRunAll()
    batch.running = true
    batch.total = data.total
    batch.done = 0; batch.ok = 0; batch.fail = 0
    batch.skipped = data.skipped || 0; batch.current = null; batch.current_list = []
    ElMessage.success(`已提交 ${data.total} 个任务后台运行（最多 ${data.concurrency || 5} 个并发`
      + (data.queued ? `，${data.queued} 个排队` : '') + '）')
    startBatchPolling()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const reportVisible = ref(false)
const reportLoading = ref(false)
const report = ref(null)
const expanded = ref([])
function showReport(rep) {
  report.value = rep
  expanded.value = (rep.items || []).map((i) => i.plugin_id)
  reportVisible.value = true
}

async function openReport(row) {
  reportVisible.value = true
  reportLoading.value = true
  report.value = null
  try {
    const data = await llmTestTaskGet(row.id)
    if (!data.last_report) { ElMessage.warning('该任务还没有测试结果'); reportVisible.value = false; return }
    showReport(data.last_report)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    reportLoading.value = false
  }
}

// ===================== 历史测试记录 =====================
const historyVisible = ref(false)
const historyLoading = ref(false)
const historyTask = ref(null)
const historyRows = ref([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historySize = 10

async function loadHistory() {
  historyLoading.value = true
  try {
    const data = await llmTestTaskRuns(historyTask.value.id,
                                       { limit: historySize, offset: (historyPage.value - 1) * historySize })
    historyRows.value = data.rows || []
    historyTotal.value = data.total || 0
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    historyLoading.value = false
  }
}

function openHistory(row) {
  historyTask.value = row
  historyPage.value = 1
  historyRows.value = []
  historyTotal.value = 0
  historyVisible.value = true
  loadHistory()
}

function onHistoryPage(p) {
  historyPage.value = p
  loadHistory()
}

async function viewRunReport(run) {
  reportVisible.value = true
  reportLoading.value = true
  report.value = null
  try {
    const data = await llmTestRunGet(run.id)
    if (!data.report) { ElMessage.warning('该历史记录缺少报告内容'); reportVisible.value = false; return }
    showReport(data.report)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    reportLoading.value = false
  }
}

// 触发浏览器下载（responseType=blob；后端出错时拿到的其实是一段 JSON 错误体）
async function triggerDownload(blob, filename) {
  if (blob.type && blob.type.includes('json')) {
    const j = JSON.parse(await blob.text())
    ElMessage.error(j.msg || '报告下载失败')
    return
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ===================== PDF 下载 =====================
async function onDownloadPdf(row) {
  try {
    const blob = await llmTestReportPdf(row.id)
    await triggerDownload(blob, `LLM测试报告_${row.name || row.id}.pdf`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// 历史列表里某一次运行的报告
async function onDownloadRunPdf(run) {
  try {
    const blob = await llmTestRunPdf(run.id)
    await triggerDownload(blob, `LLM测试报告_${run.task_name || run.task_id}_${run.run_time}.pdf`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// 报告弹窗「导出 PDF」：有 run_id 走该次历史精确下载，否则退回任务最近一次
async function onExportReportPdf() {
  const rep = report.value
  if (!rep) return
  try {
    const blob = rep.run_id ? await llmTestRunPdf(rep.run_id)
                            : await llmTestReportPdf(rep.task_id)
    await triggerDownload(blob, `LLM测试报告_${rep.task_name || rep.task_id}_${rep.run_time || ''}.pdf`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}
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
.muted { color: #8a90a5; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
.field-hint { font-size: 11.5px; color: #98a0b3; line-height: 1.6; }
.plug-tag { margin-right: 4px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
.sub-time { font-size: 11px; color: #98a0b3; }
.name-main { font-size: 13px; color: #3b3f52; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.name-desc { font-size: 11.5px; color: #98a0b3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.res-ok { color: #1a9c56; }
.res-bad { color: #d64541; }
.rule-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.turn-chip { flex: none; font-size: 11.5px; color: #6366f1; background: rgba(99, 102, 241, 0.08);
  border-radius: 999px; padding: 2px 8px; }
.prompt-item { margin-right: 8px; }
.turn-block { margin-bottom: 8px; }
.turn-q { font-size: 12.5px; color: #3b3f52; font-weight: 600; margin-bottom: 3px; }
.op-btns { display: flex; align-items: center; flex-wrap: nowrap; gap: 0; }
.op-btns .el-button + .el-button { margin-left: 8px; }
.pager { display: flex; justify-content: center; margin-top: 12px; }
.detail-text { white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.6; color: #5a607a; }
.report-head { display: flex; align-items: center; font-size: 13px; color: #3b3f52; flex-wrap: wrap; }
.sec-label { font-size: 12px; color: #8a90a5; margin: 8px 0 4px; }
.err-line { color: #d64541; font-size: 12.5px; margin: 6px 0; }
.content-pre {
  margin: 0; max-height: 220px; overflow: auto;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px; line-height: 1.55; color: #3b3f52;
  background: #f6f7fb; border: 1px solid #e6e9f2; border-radius: 8px;
  padding: 8px 12px; white-space: pre-wrap; word-break: break-all;
}
</style>
