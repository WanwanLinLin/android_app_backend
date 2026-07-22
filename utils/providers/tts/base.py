from abc import ABC, abstractmethod


class TTSProviderBase(ABC):
    
    @abstractmethod
    async def text_to_speak(self, text, conn):
        pass