import re
import time
import uuid
import json
import base64
import aiohttp
import asyncio
import aiofiles
import subprocess
from utils.common.enumTaskType import WebsocketConnectionEvent
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url: str = config.get("url")
        self.voice = config.get("voice")
        self.tag = config.get("tag")
        # 参数键 2026-10-22 起统一为 params（原 additional_param）；回退读旧键兼容外部配置
        self.params = config.get("params") or config.get("additional_param") or {}
        self.audio_index = 0
        self.token = config.get("apikey")
        self.start_time = time.perf_counter()

    def custom_text_front(self, text):
            t1 = self.remove_emoji_regex(text)
            t2 = self.clean_markdown_super(t1)
            return t2
            
    def remove_emoji_regex(self, text):
        return ''.join(char for char in text if unicodedata.category(char) != 'So')
        
    def clean_markdown_super(self, text):
        # 1. 移除代码块 ```...```
        text = re.sub(r'```[\s\S]*?```', '', text)
        
        # 2. 移除行内代码 `...`
        text = re.sub(r'`', '', text)
        
        # 3. 移除所有标题 #
        text = re.sub(r'#', '', text)
        
        # 4. 移除粗体/斜体 ** * __ _
        text = re.sub(r'\*\*|\*|__|_', '', text)
        
        # 5. 处理链接 [文字](链接) → 只保留文字
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
        
        # 6. 移除图片 ![]()
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # ====================== 修复：保留百分比负号 ======================
        # 第一步：保护 百分比前面的负号（-16.7% 这种）
        text = re.sub(r'(-\d+\.?\d*%)', r'#NEG#\1', text)

        # 第二步：保护 温度区间里的减号
        text = re.sub(r'(\d|℃)\s*-\s*(?=\d|℃)', r'\1#TEMP#', text)

        # 第三步：删除剩下的所有 - + *（列表符号、无用符号）
        text = re.sub(r'[-+*]', '', text)

        # 第四步：恢复百分比负号
        text = text.replace('#NEG#', '负')

        # 第五步：恢复温度区间
        text = text.replace('#TEMP#', '至')
        # ==================================================================
        
        # 8. 移除引用 >
        text = re.sub(r'>', '', text)
        
        # 9. 移除表格 |
        text = re.sub(r'\|', '', text)
        
        # 10. 移除分割线
        text = re.sub(r'-{3,}|\*{3,}|={3,}', '', text)
        
        # 11. 清理多余空格、空行
        text = re.sub(r'\n+', '\n', text).strip()
        text = re.sub(r' +', ' ', text)
        
        return text

    async def text_to_speak(self, text, conn):
        nums = 0
        text = self.custom_text_front(text)
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
                        "input_text": text,
                        "key_hopesen": self.token,
                        "tag": self.tag,
                        "voice": self.voice,
                        "fmt": "pcm"}) as response:
                        audio_data = await response.read()
                        async with aiofiles.open(_save_path, "wb") as f:
                            await f.write(audio_data)
                        # command = f"ffmpeg -i {_save_path} -ar 16000 -c:a pcm_s16le {save_path}"
                        if "origin_sample_rate" in self.params:
                            origin_sample_rate = self.params["origin_sample_rate"]
                        else: origin_sample_rate = 24000
                        command = f"ffmpeg -f s16le -ar {origin_sample_rate} -ac 1 -i {_save_path} -f s16le -ar 16000 {save_path}"
                        # print(f"save_path is {save_path}")
                        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        output, error = await process.communicate()
                        LOG(f"合成的文本：{text} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")            
                        reader = AsyncWavReader(
                            path=save_path,
                            frame_size=320,
                            conn=conn
                        )
                        await reader.open()
                        while conn.is_active:
                            if conn.status == WebsocketConnectionEvent.TALKING.value: break  # 打断tts数据传输
                            data1 = await reader.read_frame()
                            if not data1: break
                            if len(data1) < reader.frame_bytes:
                                # 尾帧补零而不是丢弃：硬截断会在句尾留下波形跳变（听感为"咔"声），
                                # 补齐后仍是完整 320 字节帧，不会被 opus 编码器截断
                                data1 += b'\x00' * (reader.frame_bytes - len(data1))
                                conn.tts_data_queue.put(data1)
                                break

                            conn.tts_data_queue.put(data1)

                        await reader.close()
                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue