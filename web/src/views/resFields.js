// 资源字段定义，供列表与表单动态渲染
// type: text | textarea | json  json 字段提交前 JSON.parse，展示时 JSON.stringify
// 2026-10-22：旧资源池（TTS/ASR/LLM Factories）页面已下线，资源管理统一走
// 「基础插件 + 个性插件」（见 BasePlugins.vue / CustomPlugins.vue），此处仅保留对话模板。
export const RES_FIELDS = {
  CHATTEMPLATE: {
    label: '对话模板',
    fields: [
      { key: 'module_path', label: '模板路径', type: 'text', required: true, placeholder: '如 utils.core.webrtc_aec3.voice_handler' },
      { key: 'desc', label: '描述', type: 'text', required: true },
      // hideInTable：内容太长不进表格列，仅在新增/编辑表单与「查看」弹窗中展示
      { key: 'content', label: '协议文档(JSON)', type: 'textarea', required: false, hideInTable: true, placeholder: '可粘贴 JSON 协议/配置文档全文，查看弹窗中格式化展示' }
    ]
  }
}
