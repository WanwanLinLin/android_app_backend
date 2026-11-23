import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物输出到项目根目录的 dist/（需求：构建代码放在 dist 目录）
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  build: {
    outDir: fileURLToPath(new URL('../dist', import.meta.url)),
    emptyOutDir: true
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // 开发态把 /v1 代理到后端，避免跨域；生产由部署层（nginx）同源转发
      // 容器里跑 dev server 时可用 VITE_PROXY_TARGET 指到宿主机
      '/v1': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8852',    //本地开发
        // target: 'http://113.108.106.173:8852',  // 线上
        changeOrigin: true
      }
    }
  }
})
