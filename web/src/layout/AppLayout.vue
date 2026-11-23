<template>
  <el-container style="height: 100vh">
    <el-aside width="232px" class="aside">
      <div class="brand">
        <div class="logo-mark">
          <el-icon :size="20"><Cpu /></el-icon>
        </div>
        <div class="brand-text">
          <div class="brand-title grad-text">数字人资源后台</div>
          <div class="brand-sub">Digital Human Console</div>
        </div>
      </div>

      <div class="menu-caption">管理</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/tenants">
          <el-icon><OfficeBuilding /></el-icon>
          <span>租户管理</span>
        </el-menu-item>
        <el-menu-item index="/sessions">
          <el-icon><ChatLineSquare /></el-icon>
          <span>对话记录</span>
        </el-menu-item>
      </el-menu>

      <div class="menu-caption">插件体系</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/basePlugins">
          <el-icon><Grid /></el-icon>
          <span>基础插件</span>
        </el-menu-item>
        <el-menu-item index="/customPlugins">
          <el-icon><MagicStick /></el-icon>
          <span>个性插件</span>
        </el-menu-item>
        <el-menu-item index="/chatTemplate">
          <el-icon><Document /></el-icon>
          <span>对话模板</span>
        </el-menu-item>
      </el-menu>

      <div class="menu-caption">插件测试</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/llmAutoTest">
          <el-icon><Aim /></el-icon>
          <span>LLM自动化测试</span>
        </el-menu-item>
      </el-menu>

      <div class="menu-caption">知识库</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/kb/ragflow">
          <el-icon><Notebook /></el-icon>
          <span>ragflow</span>
        </el-menu-item>
      </el-menu>

      <div class="aside-foot">
        <div class="foot-dot"></div>
        <span>{{ today }}</span>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="crumb">
          <el-icon class="crumb-ic"><Location /></el-icon>
          <span class="title">{{ $route.meta.title || '' }}</span>
        </div>
        <div class="user-area">
          <el-dropdown trigger="click" @command="onUserCommand" popper-class="user-menu-popper">
            <div class="user-trigger">
              <el-avatar :size="32" class="avatar">{{ (auth.username || '?').slice(0, 1).toUpperCase() }}</el-avatar>
              <span class="uname">{{ auth.username }}</span>
              <el-tag v-if="auth.isAdmin" size="small" type="warning" effect="light" round>管理员</el-tag>
              <el-tag v-else-if="auth.role" size="small" type="info" effect="light" round>{{ auth.role }}</el-tag>
              <el-icon class="caret"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="settings">
                  <el-icon><Setting /></el-icon>设置
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" round plain type="danger" @click="onLogout">
            <el-icon style="margin-right:4px"><SwitchButton /></el-icon>退出
          </el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  Cpu, OfficeBuilding, MagicStick,
  Document, Location, SwitchButton, ChatLineSquare, Grid, Aim, Notebook, Setting, ArrowDown
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { logout } from '@/api'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

// 租户资源页（/tenants/:id/resources）高亮「租户管理」
const activeMenu = computed(() => {
  if (route.path.startsWith('/tenants')) return '/tenants'
  if (route.path.startsWith('/kb/ragflow')) return '/kb/ragflow'
  return route.path
})

const today = new Date().toLocaleDateString('zh-CN', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
})

// 本地 role 可能是旧值（历史登录未存、或管理员改过角色），进后台时向后端对齐一次
onMounted(() => { auth.refreshMe() })

// 头像下拉菜单：设置 / 退出登录
function onUserCommand(cmd) {
  if (cmd === 'settings') router.push('/settings')
  else if (cmd === 'logout') onLogout()
}

async function onLogout() {
  try { await logout() } catch (e) { /* 忽略登出接口异常，本地照常清理 */ }
  auth.clear()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<style scoped>
.aside {
  background: linear-gradient(180deg, #ffffff 0%, #f6f7ff 100%);
  border-right: 1px solid rgba(99, 102, 241, 0.12);
  display: flex; flex-direction: column;
  position: relative;
}
.brand { display: flex; align-items: center; gap: 10px; padding: 18px 16px 14px; }
.logo-mark {
  width: 38px; height: 38px; border-radius: 12px; flex: none;
  background: var(--dh-gradient);
  display: flex; align-items: center; justify-content: center; color: #fff;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
}
.brand-title { font-weight: 700; font-size: 15.5px; line-height: 1.2; }
.brand-sub { font-size: 10.5px; color: #9aa1b5; letter-spacing: 0.4px; margin-top: 2px; }

.menu-caption {
  font-size: 11px; color: #a0a6ba; padding: 10px 20px 6px;
  letter-spacing: 1.5px; font-weight: 600;
}
.menu { border-right: none !important; background: transparent !important; padding: 0 10px; }
.menu .el-menu-item {
  border-radius: 10px; margin-bottom: 4px; height: 44px;
  color: #4b5163; transition: all 0.18s ease;
}
.menu .el-menu-item:hover { background: rgba(99, 102, 241, 0.07) !important; color: #4338ca; }
.menu .el-menu-item.is-active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.13), rgba(6, 182, 212, 0.13)) !important;
  color: #4338ca !important; font-weight: 600;
  box-shadow: inset 3px 0 0 #6366f1;
}

.aside-foot {
  margin-top: auto; padding: 14px 20px; font-size: 12px; color: #98a0b3;
  display: flex; align-items: center; gap: 8px; border-top: 1px dashed rgba(99, 102, 241, 0.15);
}
.foot-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.18); }

.header {
  display: flex; align-items: center; justify-content: space-between;
  background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(8px);
  border-bottom: 1px solid rgba(99, 102, 241, 0.10);
}
.crumb { display: flex; align-items: center; gap: 8px; }
.crumb-ic { color: #6366f1; }
.header .title { font-size: 16.5px; font-weight: 650; color: #23283b; letter-spacing: 0.3px; }
.user-area { display: flex; align-items: center; gap: 10px; }
.user-trigger {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 4px 8px; border-radius: 10px; outline: none;
  transition: background 0.18s ease;
}
.user-trigger:hover { background: rgba(99, 102, 241, 0.07); }
/* el-dropdown 会在触发区外再包一层 focusable span，对齐交给外层 flex */
.user-area :deep(.el-tooltip__trigger) { display: flex; align-items: center; outline: none; }
.caret { color: #9aa1b5; font-size: 12px; }
.avatar {
  background: var(--dh-gradient); color: #fff; font-weight: 700;
  box-shadow: 0 3px 10px rgba(99, 102, 241, 0.3);
}
.uname { color: #4b5163; font-size: 14px; font-weight: 500; }

.main { padding: 20px 22px; overflow-y: auto; }

/* 页面切换过渡 */
.page-enter-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.page-leave-active { transition: opacity 0.15s ease; }
.page-enter-from { opacity: 0; transform: translateY(10px); }
.page-leave-to { opacity: 0; }
</style>
