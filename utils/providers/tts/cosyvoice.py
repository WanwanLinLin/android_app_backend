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
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=aiohttp.TCPConnector(ssl=False)) as session:
                    async with session.post(self.url, json={
                        "input": text,
                        "voice": self.voice,
                        "response_format": "pcm"}) as response:
                        audio_data = await response.read()
                        async with aiofiles.open(_save_path, "wb") as f:
                            await f.write(audio_data)
                
                        # audio = AudioSegment.from_wav(_save_path)
                        # # 可选：确认一下原始采样率
                        # # 2. 修改采样率为16kHz
                        # audio_16k = audio.set_frame_rate(16000)
                        # audio_16k = audio_16k.set_sample_width(2)
                        # # audio_16k = audio_16k + 30
                        # # 3. 导出转换后的音频文件
                        # audio_16k.export(save_path, format='wav')
                        # command = f"ffmpeg -i {_save_path} -ar 16000 -c:a pcm_s16le {save_path}"
                        command = f"ffmpeg -f s16le -ar 24000 -ac 1 -i {_save_path} -f s16le -ar 16000 {save_path}"
                        # print(f"save_path is {save_path}")
                        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        output, error = await process.communicate()
                        LOG(f"合成的文本：{text} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")
                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue