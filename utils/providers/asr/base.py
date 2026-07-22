from abc import ABC, abstractmethod


class ASRProviderBase(ABC):
    
    @abstractmethod
    async def speech_to_text(self, file_path: str, conn):
        """将语音数据转换为文本"""
        pass