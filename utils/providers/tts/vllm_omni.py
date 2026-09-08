import re
import time
import unicodedata
import uuid
import json
import httpx
import base64
import aiohttp
import asyncio
import aiofiles
import subprocess
import audioop

import numpy as np
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader
from datetime import datetime
from queue import Queue
from collections import deque


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        self.additional_param = config.get("additional_param", {})
        self.delay_q = deque()
        self.running = True
    
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

    async def __text_to_speak(self, text, conn):
        text = self.custom_text_front(text)
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".pcm"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".pcm"
            if not text: return save_path
            # print(f"原始音频保存路径：{_save_path}")
            # print(f"采样后的音频保存路径：{save_path}")
            try:
                start_time = time.perf_counter()
                input_data = {
                    "input": text,
                    "task_type": "Base",
                    # "ref_audio": "http://113.108.106.173:8856/files/others/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_audio": "file:///data/hbh/cproject/vllm-omni/audios/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_text": "欢迎来到故宫博物院，这里是明清两代的皇家宫殿。",
                    "voice": self.voice,
                    "stream": True,
                    "response_format": "pcm",
                    "non_streaming_mode": False
                }
                if self.additional_param:
                    input_data.update(self.additional_param)
                nums = 0
                state = None
                buffer = bytearray()
                chunk_nums = 0
                async with httpx.AsyncClient() as client:
                    # 发起流式请求
                    async with client.stream("POST", self.url, json=input_data, timeout=300) as response:
                        response.raise_for_status()

                        # 异步迭代二进制数据块
                        async for chunk in response.aiter_bytes(chunk_size=320):
                            if chunk:
                                chunk_nums += 1
                                # # 跳过静音数据
                                # if chunk_nums <= 24: continue
                                converted, state = audioop.ratecv(
                                    chunk, 2, 1, 24000, 16000, state
                                )
                                buffer.extend(converted)
                                while len(buffer) >= 640:
                                    # 取出前 320 字节
                                    data = buffer[:640]
                                    del buffer[:640]
                                    # 处理 data（正好 320 字节）
                                    # print(f"{datetime.now()} len(data) is {len(data)} || len(converted) is {len(converted)}")
                                    conn.tts_data_queue.put(bytes(data))
                        # 循环结束后，如果缓冲区有剩余（< 320 字节）
                        if buffer:
                            # 补零到 320 字节
                            padding_length = 640 - len(buffer)
                            buffer.extend(b'\x00' * padding_length)  # 补静音（零值）
                            conn.tts_data_queue.put(bytes(buffer))

                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue
    
    async def _text_to_speak(self, text, conn):
        text = self.custom_text_front(text)
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".pcm"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".pcm"
            if not text: return save_path
            # print(f"原始音频保存路径：{_save_path}")
            # print(f"采样后的音频保存路径：{save_path}")
            try:
                start_time = time.perf_counter()
                input_data = {
                    "input": text,
                    "task_type": "Base",
                    # "ref_audio": "http://113.108.106.173:8856/files/others/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_audio": "file:///data/hbh/cproject/vllm-omni/audios/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_text": "欢迎来到故宫博物院，这里是明清两代的皇家宫殿。",
                    "voice": self.voice,
                    "stream": True,
                    "response_format": "pcm",
                    "non_streaming_mode": False
                }
                if self.additional_param:
                    input_data.update(self.additional_param)
                nums = 0
                state = None
                buffer = bytearray()
                chunk_nums = 0
                async with httpx.AsyncClient() as client:
                    # 发起流式请求
                    async with client.stream("POST", self.url, json=input_data, timeout=300) as response:
                        response.raise_for_status()

                        # 异步迭代二进制数据块
                        async for chunk in response.aiter_bytes(chunk_size=320):
                            if chunk:
                                chunk_nums += 1
                                # # 跳过静音数据
                                if chunk_nums <= 20: continue
                                converted, state = audioop.ratecv(
                                    chunk, 2, 1, 24000, 16000, state
                                )
                                buffer.extend(converted)
                                while len(buffer) >= 640:
                                    # 取出前 320 字节
                                    data = buffer[:640]
                                    del buffer[:640]
                                    # 处理 data（正好 320 字节）
                                    # print(f"{datetime.now()} len(data) is {len(data)} || len(converted) is {len(converted)}")
                                    # conn.tts_data_queue.put(bytes(data))
                                    self.delay_q.append(bytes(data))
                        # 循环结束后，如果缓冲区有剩余（< 320 字节）
                        if buffer:
                            # 补零到 320 字节
                            padding_length = 640 - len(buffer)
                            buffer.extend(b'\x00' * padding_length)  # 补静音（零值）
                            # conn.tts_data_queue.put(bytes(buffer))
                            self.delay_q.append(bytes(buffer))
                        
                        self.running = False
                        LOG(f"vllm-omni tts thread done | {text}", "DEBUG")
                        return save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue
    
    async def deplay_push(self, text, conn):
        flag = True
        start_time = time.perf_counter()
        while 1:
            if len(self.delay_q) > 35: break
            else: await asyncio.sleep(0.001)
        while self.running or len(self.delay_q):
            if len(self.delay_q):
                audio = self.delay_q.popleft()
                conn.tts_data_queue.put(audio)
                if flag:
                    push_first_frame_time = time.perf_counter() - start_time
                    flag = False
            else:
                await asyncio.sleep(0.001)
        
        LOG(f"vllm-omni push thread done | {text} | cost {round(push_first_frame_time, 5)} seconds", "DEBUG")
    
    async def text_to_speak(self, text, conn):
        await asyncio.gather(
            self._text_to_speak(text, conn),
            self.deplay_push(text, conn)
        )
        return 1