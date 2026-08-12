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