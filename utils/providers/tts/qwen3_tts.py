import time
import uuid
import json
import base64
import aiohttp
import audioop
import asyncio
import aiofiles
from fastapi import WebSocket, WebSocketDisconnect
import websockets
import subprocess
from utils.core.webrtc_aec3.voice_handler import ConnectionObjectCustomAec3
from utils.providers.tts.base import TTSProviderBase
from pydub import AudioSegment
from typing import Dict
from utils.getLogs import LOG
from setting import config_data
from utils.tools import AsyncWavReader

TAG = __name__


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url: str = config.get("url")
        self.voice = config.get("voice")
        self.additional_param = config.get("additional_param", {})
        self.audio_index = 0
        self.qwen3_tts_websocket = None
        self.init_tts = False
        self.token = config.get("apikey")
        self.start_time = time.perf_counter()
        
    async def initialize(self, conn: ConnectionObjectCustomAec3):
        try:
            # 对于 websockets >= 14.0，使用 additional_headers
            async with websockets.connect(
                self.url.format(token=self.token, uid="12345", voice_id=self.voice),
                # additional_headers=self.params.get("headers"),
                ping_interval=None, max_size=100*1024*1024
            ) as qwen3_tts_websocket:
                task_group =  asyncio.gather(self.receive_audio_data(conn),)
                self.qwen3_tts_websocket = qwen3_tts_websocket
                LOG(f"{TAG} 建立链接成功", "DEBUG")
                while conn.is_active:
                    await asyncio.sleep(0.05)
                await qwen3_tts_websocket.close()
                LOG(f"{TAG} 链接断开", "DEBUG")
        except WebSocketDisconnect:
            ...
    
    async def send_tts_text(self, text: str):
        self.start_time = time.perf_counter()
        self.audio_index += 1
        request_payload = json.dumps({
            "text": text,
            "prompt": "You are a helpful assistant.<|endofprompt|>",
            "audio_index": self.audio_index
        })
        await self.qwen3_tts_websocket.send(request_payload)
    
    async def receive_audio_data(self, conn: ConnectionObjectCustomAec3):
        try:
            state = None
            buffer = bytearray()
            while conn.is_active:
                res = await self.qwen3_tts_websocket.recv()
                if conn.status == 1:
                    state = None
                    buffer = bytearray()
                    self.audio_index = 0
                    continue  # 打断tts数据传输
                if isinstance(res, str):
                    res = json.loads(res)
                    if res.get("audio_index", 0) == 1:
                        LOG(f"{TAG} 收到首音频时间 {round((time.perf_counter() - self.start_time), 5)} 秒")
                    if buffer:
                        # 补零到 320 字节
                        padding_length = 640 - len(buffer)
                        buffer.extend(b'\x00' * padding_length)  # 补静音（零值）
                        conn.tts_data_queue.put(bytes(buffer))
                    state = None
                    buffer = bytearray()
                    self.audio_index = 0
                    # 发送缓存的数据
                    LOG(f"{TAG} recv str {res}")
                elif isinstance(res, (bytes, bytearray)):
                    converted, state = audioop.ratecv(
                        res, 2, 1, 24000, 16000, state
                    )
                    buffer.extend(converted)
                    while len(buffer) >= 640:
                        # 取出前 320 字节
                        data = buffer[:640]
                        del buffer[:640]
                        # 处理 data（正好 320 字节）
                        # print(f"{datetime.now()} len(data) is {len(data)} || len(converted) is {len(converted)}")
                        conn.tts_data_queue.put(bytes(data))
                        
        except websockets.exceptions.ConnectionClosedOK:
            ...
     
    async def text_to_speak(self, text, conn):
        if not self.init_tts:
            # await self.initialize(conn)
            asyncio.create_task(self.initialize(conn))
        while not self.init_tts:
            if not self.qwen3_tts_websocket: await asyncio.sleep(0.001)
            else:
                self.init_tts = True
                break
        await self.send_tts_text(text)
        return 1
      
      
      
        
    # async def text_to_speak(self, text, conn):
    #     nums = 0
    #     for i in range(5):
    #         nums += 1
    #         try:
    #             start_time = time.perf_counter()
    #             _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
    #             save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".wav"
    #             request_json = {
    #                 "model": "tts-1", 
    #                 "input": text,
    #                 "voice": self.voice,
    #                 "speed": 1.0,
    #                 "response_format": "pcm",
    #             }
    #             if self.additional_param:
    #                 request_json.update(self.additional_param)
    #             async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
    #                 async with session.post(self.url, json=request_json) as response:
    #                     if response.status != 200: 
    #                         LOG(f"Error msg: {text}", "DEBUG")
    #                         raise ValueError(await response.read())
    #                     with open(_save_path, "wb") as f:
    #                         f.write(await response.read())
                    
    #                 command = f"ffmpeg -f s16le -ar 24000 -ac 1 -i {_save_path} -f s16le -ar 16000 {save_path}"
    #                 # print(f"save_path is {save_path}")
    #                 process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #                 output, error = await process.communicate()
    #                 LOG(f"合成的文本：{text} || 花费时间：{time.perf_counter() - start_time} 秒", "DEBUG")
    #                 reader = AsyncWavReader(
    #                     path=save_path,
    #                     frame_size=320,
    #                     conn=conn
    #                 )
    #                 await reader.open()
    #                 while conn.is_active:
    #                     if conn.status == 1: break  # 打断tts数据传输
    #                     data1 = await reader.read_frame()
    #                     if len(data1) < 160 * 2:
    #                         # Last partial frame
    #                         # data1 += b'\x00' * (320 - len(data1))
    #                         # conn.tts_data_queue.put(data1)
    #                         break

    #                     conn.tts_data_queue.put(data1)

    #                 await reader.close()
    #                 return save_path
    #         except Exception as e:
    #             LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
    #             # return 0
    #             continue
