<template>
  <div class="je-node">
    <div class="je-row" :style="{ paddingLeft: depth * 18 + 'px' }">
      <!-- 展开/折叠 -->
      <span v-if="isContainer" class="je-caret" @click="expanded = !expanded">
        <el-icon class="je-caret-icon" :class="{ rot: expanded }"><ArrowRight /></el-icon>
      </span>
      <span v-else class="je-caret ph"></span>

      <!-- 键名（对象子项可改名；数组元素显示下标） -->
      <el-input v-if="!inArray" v-model="keyDraft" size="small" class="je-key"
                @change="onRename" />
      <span v-else class="je-idx">[{{ keyName }}]</span>
      <span class="je-colon">:</span>

      <!-- 叶子值编辑（keyDraft/valDraft 本地草稿：el-input 纯受控不回写 update:modelValue 会被内部还原，导致无法输入） -->
      <template v-if="!isContainer">
        <el-input v-if="type === 'string'" v-model="valDraft" size="small" class="je-val"
                  @change="(v) => set(String(v))" />
        <el-input v-else-if="type === 'number'" v-model="valDraft" size="small" class="je-val"
                  @change="commitNumber" placeholder="数字" />
        <el-switch v-else-if="type === 'boolean'" :model-value="value" size="small"
                   @change="(v) => set(!!v)" />
        <span v-else class="je-null">null</span>
      </template>
      <!-- 容器摘要 -->
      <span v-else class="je-badge" @click="expanded = !expanded">
        {{ isArray ? `[ ${childKeys.length} 项 ]` : `{ ${childKeys.length} 个字段 }` }}
      </span>

      <!-- 类型切换 -->
      <el-dropdown trigger="click" @command="changeType">
        <el-button link size="small" class="je-type-btn">{{ type }}</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="t in TYPES" :key="t" :command="t">
              {{ t }}<span v-if="t === type" class="je-cur">（当前）</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button link type="danger" size="small" class="je-del" @click="remove">
        <el-icon><Delete /></el-icon>
      </el-button>
    </div>

    <!-- 递归子节点 -->
    <template v-if="isContainer && expanded">
      <JsonNode v-for="ck in childKeys" :key="String(ck)" :parent="value" :key-name="ck"
                :depth="depth + 1" :ctx="ctx" />
      <div class="je-add" :style="{ paddingLeft: (depth + 1) * 18 + 22 + 'px' }">
        <el-button link type="primary" size="small" @click="addChild">
          <el-icon style="margin-right:2px"><Plus /></el-icon>{{ isArray ? '添加元素' : '添加字段' }}
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup>
// JSON 树编辑器的递归节点：直接对父 reactive 容器增删改，改完 ctx.bump() 通知外层序列化回 model
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight, Delete, Plus } from '@element-plus/icons-vue'

defineOptions({ name: 'JsonNode' })

const props = defineProps({
  parent: { type: [Object, Array], required: true },
  keyName: { type: [String, Number], required: true },
  depth: { type: Number, default: 0 },
  ctx: { type: Object, required: true }  // { bump }
})

const TYPES = ['string', 'number', 'boolean', 'null', 'object', 'array']

const value = computed(() => props.parent[props.keyName])
const inArray = computed(() => Array.isArray(props.parent))
const isArray = computed(() => Array.isArray(value.value))
const isObject = computed(() => value.value !== null && typeof value.value === 'object' && !isArray.value)
const isContainer = computed(() => isArray.value || isObject.value)
const type = computed(() => {
  const v = value.value
  if (v === null || v === undefined) return 'null'
  if (Array.isArray(v)) return 'array'
  return typeof v
})
const childKeys = computed(() => {
  if (isArray.value) return value.value.map((_, i) => i)
  if (isObject.value) return Object.keys(value.value)
  return []
})

const expanded = ref(true)

// —— 本地输入草稿 ——
// el-input 在「只绑 :model-value 不接 update:modelValue」时，handleInput 内部
// 会在 nextTick 调 setNativeInputValue() 把 DOM 还原成 model-value，导致打字被吞。
// 改用 v-model 绑本地草稿：打字只动草稿（无回环），失焦/回车 @change 时才写回树。
const keyDraft = ref(String(props.keyName))
const valDraft = ref(value.value === null || value.value === undefined ? '' : String(value.value))

// 外部数据变化（切换记录、树整体重载、键被改名）时同步草稿
watch(() => props.keyName, (k) => { keyDraft.value = String(k) })
watch(value, (v) => { valDraft.value = v === null || v === undefined ? '' : String(v) })

function set(v) {
  props.parent[props.keyName] = v
  props.ctx.bump()
}

function commitNumber(v) {
  const n = Number(v)
  if (v === '' || v === null || Number.isNaN(n)) {
    ElMessage.warning('请输入合法数字')
    return
  }
  set(n)
}

// 改名：原位替换并保持其余键的顺序不变
function onRename(newRaw) {
  if (inArray.value) return
  const nk = String(newRaw).trim()
  const old = props.keyName
  if (!nk || nk === old) return
  if (Object.prototype.hasOwnProperty.call(props.parent, nk)) {
    ElMessage.warning(`键名 "${nk}" 已存在，改名未生效`)
    return
  }
  const entries = Object.entries(props.parent)
  const idx = entries.findIndex(([k]) => k === old)
  entries[idx] = [nk, entries[idx][1]]
  for (const k of Object.keys(props.parent)) delete props.parent[k]
  for (const [k, val] of entries) props.parent[k] = val
  props.ctx.bump()
}

function changeType(t) {
  if (t === type.value) return
  const v = value.value
  let nv
  switch (t) {
    case 'string': nv = v === null || v === undefined ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v)); break
    case 'number': { const n = Number(v); nv = Number.isNaN(n) ? 0 : n; break }
    case 'boolean': nv = Boolean(v); break
    case 'null': nv = null; break
    case 'object':
      nv = isObject.value ? v : (isArray.value ? Object.fromEntries(v.map((x, i) => [i, x])) : {})
      break
    case 'array': nv = isArray.value ? v : []; break
    default: return
  }
  set(nv)
}

function remove() {
  if (inArray.value) props.parent.splice(Number(props.keyName), 1)
  else delete props.parent[props.keyName]
  props.ctx.bump()
}

function uniqueKey(container) {
  let k = 'newKey', i = 1
  while (Object.prototype.hasOwnProperty.call(container, k)) k = 'newKey_' + i++
  return k
}

// 添加「子级」：写进本节点自身的容器 value.value（不是 props.parent，
// 否则会加成上一级的兄弟节点，导致深层新增总是落在第一层）
function addChild() {
  const v = value.value
  if (!v || typeof v !== 'object') return
  if (Array.isArray(v)) v.push('')
  else v[uniqueKey(v)] = ''
  expanded.value = true
  props.ctx.bump()
}
</script>

<style scoped>
.je-node { font-size: 13px; }
.je-row { display: flex; align-items: center; gap: 6px; padding: 3px 4px 3px 0; min-height: 30px; }
.je-row:hover { background: #f6f7fb; border-radius: 6px; }
.je-caret { width: 16px; display: inline-flex; align-items: center; cursor: pointer; color: #8a90a5; flex: none; }
.je-caret.ph { cursor: default; }
.je-caret-icon { transition: transform .15s; font-size: 12px; }
.je-caret-icon.rot { transform: rotate(90deg); }
.je-key { width: 150px; flex: none; }
.je-idx { width: 42px; flex: none; text-align: center; color: #8a90a5; font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
.je-colon { color: #98a0b3; flex: none; }
.je-val { flex: 1; min-width: 120px; }
.je-null { color: #c0c6d9; font-style: italic; }
.je-badge { color: #6366f1; cursor: pointer; user-select: none; font-family: ui-monospace, Consolas, monospace; font-size: 12px; background: rgba(99, 102, 241, .07); padding: 1px 8px; border-radius: 999px; }
.je-badge:hover { background: rgba(99, 102, 241, .14); }
.je-type-btn { color: #98a0b3 !important; font-size: 11px !important; flex: none; }
.je-type-btn:hover { color: #6366f1 !important; }
.je-cur { color: #c0c6d9; font-size: 11px; }
.je-del { flex: none; }
.je-add { padding: 1px 0 3px; }
</style>
