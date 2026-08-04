import uuid
import json
import base64
import aiohttp
import requests
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        
    async def text_to_speak(self, text, conn):
        nums = 0
        for i in range(5):
            nums += 1
            LOG(f"合成的文本：{text}", "DEBUG")
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".wav"
            # print(f"原始音频保存路径：{_save_path}")
            # print(f"采样后的音频保存路径：{save_path}")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=aiohttp.TCPConnector(ssl=False)) as session:
                    async with session.post(self.url, json={
                        "input": text,
                        "voice": self.voice,
                        "response_format": "wav"}) as response:
                        with open(_save_path, "wb") as f:
                            f.write(await response.read())
                
                        audio = AudioSegment.from_wav(_save_path)
                        # 可选：确认一下原始采样率
                        # 2. 修改采样率为16kHz
                        audio_16k = audio.set_frame_rate(16000)
                        audio_16k = audio_16k.set_sample_width(2)
                        # audio_16k = audio_16k + 30
                        # 3. 导出转换后的音频文件
                        audio_16k.export(save_path, format='wav')
                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue