<template>
  <div class="fade-up">
    <div class="page-card">
      <div class="toolbar">
        <div class="card-title" style="margin-bottom:0">
          <el-icon><OfficeBuilding /></el-icon>租户列表
          <span class="count-chip">{{ rows.length }}</span>
        </div>
        <div class="toolbar-right">
          <el-input v-model="keyword" placeholder="搜索租户名 / 姓名 / 电话" clearable
                    :prefix-icon="Search" style="width: 240px" />
          <el-button :icon="Refresh" round plain @click="load">刷新</el-button>
          <el-button type="primary" round @click="openAdd">
            <el-icon style="margin-right:4px"><Plus /></el-icon>新增租户
          </el-button>
        </div>
      </div>

      <el-table :data="filtered" v-loading="loading" stripe style="width: 100%"
                :header-cell-style="{ fontWeight: 600 }">
        <el-table-column prop="id" label="ID" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="tenantname" label="租户名(业务身份)" min-width="160">
          <template #default="{ row }">
            <span class="tenant-name">{{ row.tenantname }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="nickname" label="真实姓名" width="130" />
        <el-table-column label="所属管理员" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.user_id" size="small" type="info" effect="plain">
              {{ adminName(row.user_id) }}
            </el-tag>
            <span v-else class="empty-dash">未归属</span>
          </template>
        </el-table-column>
        <el-table-column prop="job" label="工作描述" show-overflow-tooltip min-width="160" />
        <el-table-column prop="phone_number" label="电话" width="140" />
        <el-table-column prop="create_time" label="创建时间" width="170" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" round plain type="primary" @click="goResources(row)">
              <el-icon style="margin-right:3px"><Files /></el-icon>资源管理
            </el-button>
            <el-button size="small" round plain @click="openEdit(row)">编辑</el-button>
            <el-button size="small" round plain type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">
            <el-icon :size="36" color="#c0c6d9"><Box /></el-icon>
            <p>{{ keyword ? '没有匹配的租户' : '暂无租户，点击右上角新增' }}</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 新增 / 编辑租户 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑租户' : '新增租户'" width="480px" destroy-on-close append-to-body>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="110px">
        <el-form-item label="租户名" prop="tenantname">
          <el-input v-model="form.tenantname" :disabled="!!editing" placeholder="终端业务身份标识，唯一" />
        </el-form-item>
        <el-form-item label="所属管理员">
          <el-select v-model="form.user_id" clearable filterable placeholder="选择归属的后台管理员（可留空）" style="width:100%">
            <el-option v-for="u in admins" :key="u.id"
                       :label="`${u.username}${u.nickname ? ' · ' + u.nickname : ''}`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="真实姓名"><el-input v-model="form.nickname" /></el-form-item>
        <el-form-item label="工作描述"><el-input v-model="form.job" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.phone_number" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, Files, Box, OfficeBuilding } from '@element-plus/icons-vue'
import { tenantList, tenantAdd, tenantUpdate, tenantDelete, userList } from '@/api'

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const keyword = ref('')
const admins = ref([])

const formVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const editing = ref(null)
const form = reactive({ tenantname: '', user_id: null, nickname: '', job: '', phone_number: '' })
const rules = { tenantname: [{ required: true, message: '请输入租户名', trigger: 'blur' }] }

function adminName(id) {
  const u = admins.value.find((x) => x.id === id)
  return u ? (u.nickname ? `${u.username} · ${u.nickname}` : u.username) : `#${id}`
}

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter((r) =>
    [r.tenantname, r.nickname, r.phone_number].some((v) => (v || '').toLowerCase().includes(k)))
})

async function load() {
  loading.value = true
  try {
    const [list, us] = await Promise.all([tenantList(), userList()])
    rows.value = list
    admins.value = us
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function goResources(row) {
  router.push({ name: 'tenantResources', params: { id: row.id } })
}

function openAdd() {
  editing.value = null
  Object.assign(form, { tenantname: '', user_id: null, nickname: '', job: '', phone_number: '' })
  formVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    tenantname: row.tenantname, user_id: row.user_id ?? null,
    nickname: row.nickname || '',
    job: row.job || '', phone_number: row.phone_number || ''
  })
  formVisible.value = true
}

async function submitForm() {
  await formRef.value.validate().catch(() => { throw new Error('请检查必填项') })
  submitting.value = true
  try {
    if (editing.value) {
      await tenantUpdate(editing.value.id, { user_id: form.user_id, nickname: form.nickname, job: form.job, phone_number: form.phone_number })
      ElMessage.success('更新成功')
    } else {
      await tenantAdd({ tenantname: form.tenantname, user_id: form.user_id, nickname: form.nickname, job: form.job, phone_number: form.phone_number })
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

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除租户「${row.tenantname}」？（软删除）`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await tenantDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
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
.tenant-name { font-weight: 600; color: #23283b; }
.empty-dash { color: #b3bacc; font-size: 12px; }
.empty { padding: 30px 0; text-align: center; color: #98a0b3; font-size: 13px; }
</style>
