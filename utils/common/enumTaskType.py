# 导入枚举基类
from enum import Enum


# 基础插件类别 ↔ 个性插件绑定类型的映射。
# 注意：映射必须放模块级——Enum 类体内直接赋值的 dict 会被 Python 吸收成
# 枚举成员（cls.CUSTOM_OF 变成 member 而非 dict），.get 直接 AttributeError。
_CUSTOM_OF = {"TTS": "TTS_CUSTOM", "ASR": "ASR_CUSTOM", "LLM": "LLM_CUSTOM"}
_BASE_OF = {"TTS_CUSTOM": "TTS", "ASR_CUSTOM": "ASR", "LLM_CUSTOM": "LLM"}


class SourceTypeEnum(Enum):
    TTS = "TTS"
    LLM = "LLM"
    ASR = "ASR"
    FIGURE = "FIGURE"
    BACKGROUND = "BACKGROUND"
    CHATTEMPLATE = "CHATTEMPLATE"
    # 个性插件绑定类型（SourceList.type 新取值，指向 CustomPlugin 表）。
    # 旧取值 TTS/ASR/LLM 仍有效——指向三张 Factories 表的存量绑定，
    # 迁移脚本执行后 SourceList 中不再出现旧取值。
    TTS_CUSTOM = "TTS_CUSTOM"
    ASR_CUSTOM = "ASR_CUSTOM"
    LLM_CUSTOM = "LLM_CUSTOM"

    @classmethod
    def to_custom(cls, base_type: str):
        """TTS/ASR/LLM → 对应的 *_CUSTOM；非基础类别原样返回。"""
        return _CUSTOM_OF.get(base_type, base_type)

    @classmethod
    def to_base(cls, custom_type: str):
        """*_CUSTOM → 对应的基础类别；非 custom 取值原样返回。"""
        return _BASE_OF.get(custom_type, custom_type)


    
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
    SESSION_CREATE = "session_create"
    

# Websocket 客户端事件
class WebsocketClientEvent(Enum):
    WAKEUP = "wakeup"   # 客户端唤醒词打断事件
    TRANSCRIPTION = "transcription"   # 客户端语音识别结果（完整整句，非 chunk），用于客户端 ASR 模板


class ServerInternalEvent(Enum):
    TTS = "tts"     # 可以进行语音合成
    LLM_DONE = "llm_done"   # 智能体内容输出完成
    

class WebsocketConnectionEvent(Enum):
    IDLE = "idle"   # 待机状态
    TALKING = "talking"     # 对话状态