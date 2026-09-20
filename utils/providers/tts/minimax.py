import time
import uuid
import json
import base64
import aiohttp
import asyncio
import binascii
import aiofiles
from fastapi import WebSocket, WebSocketDisconnect
import websockets
import subprocess
from mybatisPlus.tts_orm import handle_audio_file
from utils.core.webrtc_aec3.voice_handler import ConnectionObjectCustomAec3
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader, md5_hash

TAG = __name__


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        self.additional_param = config.get("additional_param", {})
        self.apikey = config.get("apikey")
        self.audio_data = b''
        self.sr = 16000
        self.speed = 1.0
        self.format = "pcm"
        self.tag = config.get("tag")
    
    async def text_to_speak(self, text, conn):
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
                # conn.aec3_data_queue.put(data1[:320])
                # conn.aec3_data_queue.put(data1[320:])

            await reader.close()
            return 1
        else:
            nums = 0
            for i in range(5):
                nums += 1
                start_time = time.perf_counter()
                save_file_name = str(uuid.uuid4()) + f".{self.format}"
                _save_path = config_data["CACHE"]["tts_cache"] + save_file_name
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.apikey}"
                    }
                    payload = {
                        "text": text,
                        "stream": False,
                        "voice_setting": {
                            "voice_id": self.voice,
                            "speed": self.speed,
                            "vol": 1,
                            "pitch": 0,
                            # "emotion": "happy"
                        },
                        "audio_setting": {
                            "sample_rate": self.sr,
                            "bitrate": 128000,
                            "format": "pcm",
                            "channel": 1
                        },
                        # "pronunciation_dict": { "tone": ["处理/(chu3)(li3)", "危险/dangerous"] },
                        "subtitle_enable": False
                    }
                    payload.update(self.additional_param)
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=aiohttp.TCPConnector(ssl=False)) as session:
                        async with session.post(self.url, json=payload, headers=headers) as response:
                            resp = await response.json()
                            # LOG(f"{TAG} resp is：{resp} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")  
                            data = resp["data"]["audio"]
                            audio_data = binascii.unhexlify(data)
                            async with aiofiles.open(_save_path, "wb") as f:
                                await f.write(audio_data)
                            
                            LOG(f"{TAG} 合成的文本：{text} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")            
                            reader = AsyncWavReader(
                                path=_save_path,
                                frame_size=320,
                                conn=conn
                            )
                            await reader.open()
                            while conn.is_active:
                                if conn.status == 1: break  # 打断tts数据传输
                                data1 = await reader.read_frame()
                                if len(data1) < 160 * 2:
                                    padding_length = 640 - len(data1)
                                    data1 += b'\x00' * padding_length
                                    # Last partial frame
                                    conn.tts_data_queue.put(data1)
                                    break

                                conn.tts_data_queue.put(data1)
                            await reader.close()
                            
                            await handle_audio_file(op=False, tag=self.tag, sec_text=self.sec_text,
                                            voice=self.voice, format=self.format, sr=self.sr, recog_text=self.recog_text,
                                            save_path=save_file_name, speed=self.speed)
                            return _save_path
                except Exception as e:
                    LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                    # return 0
                    continue