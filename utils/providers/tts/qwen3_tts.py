import time
import uuid
import json
import base64
import aiohttp
import asyncio
import aiofiles
import subprocess
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader

TAG = __name__


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        
    async def text_to_speak(self, text, conn):
        nums = 0
        for i in range(5):
            nums += 1
            try:
                start_time = time.perf_counter()
                _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
                save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".wav"
                request_json = {
                    "model": "tts-1", 
                    "input": text,
                    "voice": self.voice,
                    "speed": 1.0,
                    "response_format": "pcm",
                    "language": "Chinese",
                    "instruct": "请用纯正广东话朗读" 
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                    async with session.post(self.url, json=request_json) as response:
                        if response.status != 200: 
                            LOG(f"Error msg: {text}", "DEBUG")
                            raise ValueError(await response.read())
                        with open(_save_path, "wb") as f:
                            f.write(await response.read())
                    
                    command = f"ffmpeg -f s16le -ar 24000 -ac 1 -i {_save_path} -f s16le -ar 16000 {save_path}"
                    # print(f"save_path is {save_path}")
                    process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    output, error = await process.communicate()
                    LOG(f"合成的文本：{text} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")
                    reader = AsyncWavReader(
                        path=save_path,
                        frame_size=160,
                        conn=conn
                    )
                    await reader.open()
                    while conn.is_active:
                        if conn.status == 1: break  # 打断tts数据传输
                        data1 = await reader.read_frame()
                        if len(data1) < 160 * 2:
                            # Last partial frame
                            conn.tts_data_queue.put(data1)
                            break

                        conn.tts_data_queue.put(data1)

                    await reader.close()
                    return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue
