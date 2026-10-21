<template>
  <div class="json-editor" :class="{ 'is-dark': false }">
    <div class="je-toolbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="tree">树形编辑</el-radio-button>
        <el-radio-button value="source">源码模式</el-radio-button>
      </el-radio-group>
      <div class="je-toolbar-right">
        <el-button v-if="mode === 'tree'" link type="primary" size="small" :disabled="!parsedOk" @click="expandAll(true)">展开全部</el-button>
        <el-button v-if="mode === 'source'" link type="primary" size="small" :disabled="!!sourceError" @click="formatSource">格式化</el-button>
        <el-button link type="primary" size="small" :disabled="!parsedOk" @click="resetFromSource">重置</el-button>
      </div>
    </div>

    <!-- 树形模式 -->
    <div v-if="mode === 'tree'" class="je-tree">
      <div v-if="!parsedOk" class="je-invalid">
        <el-icon><WarningFilled /></el-icon>
        当前内容不是合法 JSON，无法进入树形编辑。
        <el-button link type="primary" size="small" @click="mode = 'source'">去源码模式修正</el-button>
        <el-button link type="danger" size="small" @click="overwriteWithEmpty">置为空对象 {}</el-button>
      </div>
      <template v-else-if="isRootContainer">
        <JsonNode v-for="ck in rootKeys" :key="treeMountKey + '-' + String(ck)" :parent="treeData" :key-name="ck"
                  :depth="0" :ctx="ctx" />
        <div class="je-add je-root-add">
          <el-button link type="primary" size="small" @click="addRootChild">
            <el-icon style="margin-right:2px"><Plus /></el-icon>添加字段
          </el-button>
        </div>
      </template>
      <div v-else class="je-empty">根节点是 {{ rootType }}，仅对象 / 数组支持树形编辑，请切到源码模式。</div>
    </div>

    <!-- 源码模式 -->
    <div v-else class="je-source">
      <el-input v-model="source" type="textarea" :rows="10" :class="{ 'src-err': !!sourceError }"
                placeholder='JSON，如 {"headers": {"Authorization": "Bearer xxx"}}' @input="onSourceInput" />
      <div v-if="source && sourceError" class="je-src-error">
        <el-icon><WarningFilled /></el-icon>{{ sourceError }}
      </div>
    </div>
  </div>
</template>

<script setup>
// 多层 JSON 可视化编辑器：v-model 为 JSON 字符串（与原 textarea 字段完全兼容）
// 树形模式 = 结构化增删改；源码模式 = 文本编辑 + 实时语法校验 + 一键格式化
import { ref, computed, watch, reactive, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled, Plus } from '@element-plus/icons-vue'
import JsonNode from './JsonNode.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  resetValue: { type: String, default: '' }  // 「重置」回到的初始值（编辑打开时的原文）
})
const emit = defineEmits(['update:modelValue'])

const source = ref(props.modelValue || '')
const mode = ref('tree')

// —— 解析 ——
const parsed = ref(null)
const parseErr = ref('')
function tryParse(s) {
  if (s === '' || s === null || s === undefined) return { ok: true, value: null, empty: true }
  try {
    return { ok: true, value: JSON.parse(s), empty: false }
  } catch (e) {
    return { ok: false, err: e.message }
  }
}
function reparse() {
  const r = tryParse(source.value)
  parseErr.value = r.ok ? '' : r.err
  parsed.value = r.ok ? r.value : null
}

const sourceError = computed(() => parseErr.value)
const parsedOk = computed(() => !parseErr.value)
const isEmptySource = computed(() => (source.value || '').trim() === '')
// 空内容视为空对象：新增资源时树形区直接展示「添加字段」而不是报错提示
const isRootContainer = computed(() => isEmptySource.value || (parsed.value !== null && typeof parsed.value === 'object'))
const rootType = computed(() => Array.isArray(parsed.value) ? 'array' : (isEmptySource.value ? 'object' : typeof parsed.value))

// —— 树数据 ——
// shallowRef 持有整体容器（reactive 包装的原始对象/数组）。
// 根节点为数组时容器就是数组，序列化不会退化成 {"0":...}
const treeData = shallowRef(reactive({}))

const rootKeys = computed(() => {
  const td = treeData.value
  if (td === null || typeof td !== 'object') return []
  return Array.isArray(td) ? td.map((_, i) => i) : Object.keys(td)
})
const addRootChild = () => {
  const td = treeData.value
  if (Array.isArray(td)) td.push('')
  else td[uniqueRootKey()] = ''
  bump()
}
function uniqueRootKey() {
  const td = treeData.value
  let k = 'newKey', i = 1
  while (Object.prototype.hasOwnProperty.call(td, k)) k = 'newKey_' + i++
  return k
}

function loadTreeFromSource() {
  if (isEmptySource.value) {
    treeData.value = reactive({})
    return
  }
  if (!parsedOk.value || !isRootContainer.value) return
  treeData.value = reactive(JSON.parse(source.value))
}

function bump() {
  // 树 → JSON 字符串（缩进 2），同步外层 model。
  // emit 出去的字符串与 source.value 一致，外部回传时由 watcher 的等值守卫拦截，不会触发树重载
  const out = JSON.stringify(treeData.value, null, 2)
  source.value = out
  emit('update:modelValue', out)
}

const ctx = { bump }

function onSourceInput() {
  reparse()
  emit('update:modelValue', source.value)
}

// 进树形模式前：源码 parse 成功才灌入树（失败保留树旧态并提示）
watch(mode, (m) => {
  if (m === 'tree') {
    reparse()
    if (!parsedOk.value) return
    if (!isRootContainer.value) return
    loadTreeFromSource()
  }
})

// 外部改值（打开弹窗 resetForm 后 v-model 传入）：整体刷新。
// 等值守卫：bump 自己 emit 回传的同一字符串直接忽略，避免无谓的树重载打断正在进行的输入
watch(() => props.modelValue, (v) => {
  const nv = v || ''
  if (nv === source.value) return
  source.value = nv
  reparse()
  if (parsedOk.value && isRootContainer.value) loadTreeFromSource()
})

function formatSource() {
  reparse()
  if (!parsedOk.value) return
  source.value = JSON.stringify(parsed.value, null, 2)
  emit('update:modelValue', source.value)
  ElMessage.success('已格式化')
}

function resetFromSource() {
  const target = props.resetValue || ''
  source.value = target
  reparse()
  if (parsedOk.value && isRootContainer.value) loadTreeFromSource()
  emit('update:modelValue', target)
}

function overwriteWithEmpty() {
  const t = Array.isArray(parsed.value) ? '[]' : '{}'
  source.value = t
  reparse()
  loadTreeFromSource()
  emit('update:modelValue', t)
}

// 展开全部：通过重挂载整棵树实现（key 变化触发 JsonNode 重新创建，默认展开）
const treeMountKey = ref(0)
function expandAll() {
  loadTreeFromSource()
  treeMountKey.value++
}

// —— 挂载初始化：首次进入必须把 modelValue 灌入树，否则打开弹窗时树是空的 ——
reparse()
loadTreeFromSource()
</script>

<style scoped>
.json-editor { width: 100%; }
.je-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.je-toolbar-right { display: flex; gap: 2px; }
.je-tree {
  border: 1px solid #e6e9f2; border-radius: 8px; background: #fbfcfe;
  max-height: 380px; overflow: auto; padding: 8px 10px;
}
.je-empty, .je-invalid { color: #98a0b3; font-size: 12.5px; padding: 10px 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.je-invalid { color: #b45309; }
.je-invalid .el-icon { color: #f59e0b; }
.je-root-add { padding-left: 22px; }
.je-src-error {
  display: flex; align-items: center; gap: 5px; margin-top: 5px;
  color: #f56c6c; font-size: 12px; line-height: 1.5; word-break: break-all;
}
:deep(.src-err .el-textarea__inner) { border-color: #f56c6c; box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
