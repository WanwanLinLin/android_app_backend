<template>
  <div class="login-wrap">
    <!-- 背景装饰 -->
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="blob blob-3"></div>
    <div class="grid-overlay"></div>

    <div class="login-panel fade-up">
      <div class="login-left">
        <div class="logo-mark"><el-icon :size="30"><Cpu /></el-icon></div>
        <h1 class="slogan">数字人资源<br>管理后台</h1>
        <p class="sub">租户 · TTS · ASR · LLM · 对话模板<br>一站式资源配置与调度</p>
        <div class="deco-dots">
          <span v-for="i in 6" :key="i" class="dot" :style="{ animationDelay: i * 0.25 + 's' }"></span>
        </div>
      </div>

      <div class="login-right">
        <h2 class="login-title">欢迎回来</h2>
        <p class="login-sub">使用后台管理员账号登录</p>
        <el-form :model="form" :rules="rules" ref="formRef" @submit.prevent="onSubmit">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" size="large"
                      show-password :prefix-icon="Lock" @keyup.enter="onSubmit" />
          </el-form-item>
          <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onSubmit">
            登 录
          </el-button>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Cpu } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function onSubmit() {
  await formRef.value.validate()
  loading.value = true
  try {
    await auth.login({ username: form.username, password: form.password })
    ElMessage.success('登录成功')
    router.push({ name: 'tenants' })
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background:
    radial-gradient(900px 500px at 10% 0%, rgba(99, 102, 241, 0.16), transparent 60%),
    radial-gradient(800px 500px at 95% 100%, rgba(6, 182, 212, 0.16), transparent 55%),
    #f4f6fc;
  overflow: hidden; position: relative;
}

/* 漂浮光斑 */
.blob { position: absolute; border-radius: 50%; filter: blur(70px); opacity: 0.5; }
.blob-1 { width: 420px; height: 420px; left: -120px; top: -120px; background: #c7d2fe; animation: drift 14s ease-in-out infinite alternate; }
.blob-2 { width: 360px; height: 360px; right: -100px; bottom: -100px; background: #a5f3fc; animation: drift 18s ease-in-out infinite alternate-reverse; }
.blob-3 { width: 240px; height: 240px; left: 55%; top: 8%; background: #ddd6fe; animation: drift 11s ease-in-out infinite alternate; }
@keyframes drift {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(50px, 40px) scale(1.12); }
}
.grid-overlay {
  position: absolute; inset: 0;
  background-image: linear-gradient(rgba(99, 102, 241, 0.045) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(99, 102, 241, 0.045) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(700px 500px at 50% 50%, black, transparent 90%);
}

/* 面板 */
.login-panel {
  position: relative; z-index: 1;
  display: flex; width: 780px; max-width: 94vw; min-height: 440px;
  background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(14px);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 22px; overflow: hidden;
  box-shadow: 0 24px 70px rgba(67, 56, 202, 0.16);
}

/* 左侧品牌区 */
.login-left {
  flex: 1; padding: 44px 38px; color: #fff; position: relative;
  background: linear-gradient(150deg, #4f46e5 0%, #7c3aed 55%, #0891b2 100%);
  display: flex; flex-direction: column;
}
.login-left::after {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(300px 200px at 85% 15%, rgba(255, 255, 255, 0.18), transparent 65%);
}
.logo-mark {
  width: 56px; height: 56px; border-radius: 16px;
  background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.3);
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(6px); margin-bottom: 26px;
}
.slogan { font-size: 30px; line-height: 1.28; font-weight: 750; margin: 0 0 14px; letter-spacing: 1px; }
.sub { font-size: 13px; line-height: 1.8; opacity: 0.82; margin: 0; }
.deco-dots { margin-top: auto; display: flex; gap: 9px; }
.dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: rgba(255, 255, 255, 0.45);
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: 0.35; transform: scale(1); } 50% { opacity: 1; transform: scale(1.35); } }

/* 右侧表单区 */
.login-right { flex: 1; padding: 52px 42px; display: flex; flex-direction: column; justify-content: center; }
.login-title { font-size: 24px; font-weight: 700; margin: 0 0 6px; color: #23283b; }
.login-sub { font-size: 13px; color: #8a90a5; margin: 0 0 28px; }
.login-btn {
  width: 100%; margin-top: 6px; border: none; letter-spacing: 6px; font-weight: 600;
  background: linear-gradient(135deg, #6366f1, #06b6d4);
  transition: filter 0.2s ease, box-shadow 0.25s ease, transform 0.15s ease;
}
.login-btn:hover { filter: brightness(1.08); box-shadow: 0 10px 26px rgba(99, 102, 241, 0.4); transform: translateY(-1px); }

:deep(.el-input__wrapper) { border-radius: 10px; }

@media (max-width: 720px) {
  .login-left { display: none; }
  .login-panel { width: 92vw; }
}
</style>
