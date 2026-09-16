import os
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
from utils.tools import md5_hash
from mybatisPlus.tts_orm import handle_audio_file


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        self.additional_param = config.get("additional_param", {})
        self.delay_q = deque()
        self.running = True
        self.format = "pcm"
        self.tag = config.get("tag")
        self.audio_data = b''
        self.sr = 16000
        self.speed = 1.0
    
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
    
    async def _text_to_speak(self, text, conn):
        if len(text) < 12: use_stream = False
        else: use_stream = True
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            save_file_name = str(uuid.uuid4()) + f".{self.format}"
            _save_path = config_data["CACHE"]["tts_cache"] + save_file_name
            if not text: return _save_path
            # print(f"原始音频保存路径：{_save_path}")
            # print(f"采样后的音频保存路径：{save_path}")
            try:
                start_time = time.perf_counter()
                input_data = {
                    "input": text,
                    "task_type": "CustomVoice",
                    # "ref_audio": "http://113.108.106.173:8856/files/others/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_audio": "file:///data/hbh/cproject/vllm-omni/audios/ICL_zh_female_tianmeixiaoyu_cs_tob.wav",
                    # "ref_text": "欢迎来到故宫博物院，这里是明清两代的皇家宫殿。",
                    "voice": self.voice,
                    "stream": use_stream,
                    "response_format": self.format,
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
                                if use_stream:
                                    if chunk_nums <= 18: continue
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
                                    self.audio_data += bytes(data)
                        # 循环结束后，如果缓冲区有剩余（< 320 字节）
                        if buffer:
                            # 补零到 320 字节
                            padding_length = 640 - len(buffer)
                            buffer.extend(b'\x00' * padding_length)  # 补静音（零值）
                            # conn.tts_data_queue.put(bytes(buffer))
                            self.delay_q.append(bytes(buffer))
                            self.audio_data += bytes(buffer)
                        
                        self.running = False
                        # 保存音频文件
                        await handle_audio_file(op=False, tag=self.tag, sec_text=self.sec_text,
                                      voice=self.voice, format=self.format, sr=self.sr, recog_text=self.recog_text,
                                      save_path=save_file_name, speed=self.speed)
                        with open(_save_path, "wb") as f:
                            f.write(self.audio_data)
                        self.audio_data = b''
                        LOG(f"vllm-omni tts thread done | {text}", "DEBUG")
                        return _save_path
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue
    
    async def deplay_push(self, text, conn):
        flag = True
        start_time = time.perf_counter()
        # while 1:
        #     if len(self.delay_q) > 35: break
        #     else: await asyncio.sleep(0.001)
        while self.running or len(self.delay_q):
            if conn.status == 1: 
                LOG(f"vllm-omni 收到客户端打断消息，停止推送音频", "DEBUG")
                break
            if len(self.delay_q):
                audio = self.delay_q.popleft()
                conn.tts_data_queue.put(audio)
                # conn.aec3_data_queue.put(audio[:320])
                # conn.aec3_data_queue.put(audio[320:])
                if flag:
                    push_first_frame_time = time.perf_counter() - start_time
                    flag = False
            else:
                await asyncio.sleep(0.001)
        
        LOG(f"vllm-omni push thread done | {text} | first chunk cost {round(push_first_frame_time, 5)} seconds", "DEBUG")
    
    async def text_to_speak(self, text, conn):
        text = self.custom_text_front(text)
        self.sec_text = md5_hash(text)
        self.recog_text = text
        # 尝试使用缓存
        res = await handle_audio_file(op=True, tag=self.tag, sec_text=self.sec_text,
                                      voice=self.voice, format=self.format, sr=self.sr, speed=self.speed)
        if res:
            reader = AsyncWavReader(
                path=config_data["CACHE"]["tts_cache"] + res,
                frame_size=320,
                conn=conn
            )
            await reader.open()
            while conn.is_active:
                if conn.status == 1: break  # 打断tts数据传输
                data1 = await reader.read_frame()
                if len(data1) < 160 * 2:
                    # Last partial frame
                    # data1 += b'\x00' * (320 - len(data1))
                    # conn.tts_data_queue.put(data1)
                    break

                conn.tts_data_queue.put(data1)
                conn.aec3_data_queue.put(data1[:320])
                conn.aec3_data_queue.put(data1[320:])

            await reader.close()
            return 1
        else:
        
            await asyncio.gather(
                self._text_to_speak(text, conn),
                self.deplay_push(text, conn)
            )
            return 1