// 三类资源的字段定义，供列表与表单动态渲染
// type: text | textarea | json  json 字段提交前 JSON.parse，展示时 JSON.stringify
export const RES_FIELDS = {
  TTS: {
    label: 'TTS 音色',
    fields: [
      { key: 'type', label: '接口类型', type: 'text', required: true, placeholder: '如 generic / openai' },
      { key: 'url', label: '接口地址', type: 'text', required: true },
      { key: 'desc', label: '描述', type: 'text', required: true },
      { key: 'tag', label: '音色标签', type: 'text', required: true },
      { key: 'voice', label: '音色名称', type: 'text', required: true },
      { key: 'apikey', label: '请求密钥', type: 'text', required: true },
      { key: 'additional_param', label: '附加参数(JSON)', type: 'json', required: false }
    ]
  },
  ASR: {
    label: 'ASR 语音识别',
    fields: [
      { key: 'type', label: '接口类型', type: 'text', required: true, placeholder: '如 qwen3_asr / sensevoice' },
      { key: 'url', label: '接口地址', type: 'text', required: true },
      { key: 'desc', label: '描述', type: 'text', required: true },
      { key: 'apikey', label: '请求密钥', type: 'text', required: true },
      { key: 'params', label: '参数(JSON)', type: 'json', required: true }
    ]
  },
  LLM: {
    label: 'LLM 大模型',
    fields: [
      { key: 'type', label: '接口类型', type: 'text', required: true, placeholder: '如 generic / openai' },
      { key: 'url', label: '接口地址', type: 'text', required: true },
      { key: 'desc', label: '描述', type: 'text', required: true },
      { key: 'apikey', label: '请求密钥', type: 'text', required: true },
      { key: 'params', label: '参数(JSON)', type: 'json', required: true }
    ]
  },
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
