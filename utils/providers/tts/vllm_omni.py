import time
import uuid
import json
import httpx
import base64
import aiohttp
import asyncio
import aiofiles
import subprocess
import audioop
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        
    async def text_to_speak(self, text, conn):
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".pcm"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".pcm"
            # print(f"原始音频保存路径：{_save_path}")
            # print(f"采样后的音频保存路径：{save_path}")
            try:
                start_time = time.perf_counter()
                input_data = {
                    "input": text,
                    "task_type": "Base",
                    # "ref_audio": "http://113.108.106.173:8856/files/others/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    "ref_audio": "file:///data/hbh/cproject/vllm-omni/audios/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    "ref_text": "欢迎来到故宫博物院，这里是明清两代的皇家宫殿。",
                    "stream": True,
                    "response_format": "pcm"
                }
                nums = 0
                state = None
                async with httpx.AsyncClient() as client:
                    # 发起流式请求
                    async with client.stream("POST", self.url, json=input_data, timeout=300) as response:
                        response.raise_for_status()

                        # 异步迭代二进制数据块
                        async for chunk in response.aiter_bytes(chunk_size=160):
                            nums += 1
                            converted, state = audioop.ratecv(
                                chunk, 2, 1, 24000, 16000, state
                            )

                            conn.tts_data_queue.put(converted)

                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue