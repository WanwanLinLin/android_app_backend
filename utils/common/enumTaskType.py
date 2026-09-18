# 导入枚举基类
from enum import Enum


# 定义枚举类
class TaskTypeEnum(Enum):
    SanitationTreatment = "卫生处理"
    FaultReporting = "故障报修"
    SecurityIncident = "安全事件"
    Undefied = "undefied"
    

class SourceTypeEnum(Enum):
    TTS = "TTS"
    LLM = "LLM"
    ASR = "ASR"
    FIGURE = "FIGURE"
    BACKGROUND = "BACKGROUND"
    
    
# Websocket 服务端事件
class WebsocketServerEvent(Enum):
    INTERRUPT = "interrupt"     # 服务端中断事件
    TRANSCRIPTION = "transcription"     # 流式 asr 语音识别完成
    STOP_LISTENING = "stop_listening"   # vad 收到尾音信息，停止监听
    START_LISTENING = "start_listening"     # vad 开始监听
    ANALYSIS = "analysis"       # 服务端性能分析日志，可以用于客户端展示
    ASSISTANT = "assistant"     # 智能体回复内容
    FINISH = "finish"           # 智能体回复完成
    TTS_DONE = "tts_done"       # 推送完本轮对话所有的tts数据
    

# Websocket 客户端事件
class WebsocketClientEvent(Enum):
    WAKEUP = "wakeup"   # 客户端唤醒词打断事件


class ServerInternalEvent(Enum):
    TTS = "tts"     # 可以进行语音合成
    LLM_DONE = "llm_done"   # 智能体内容输出完成