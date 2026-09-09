import os
import base64
import hashlib
import hmac
import json
import time
import uuid
import base64
import aiohttp
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
import numpy as np
import websockets
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from utils.core.webrtc_aec3.voice_handler import ConnectionObjectCustomAec3
from utils.providers.asr.base import ASRProviderBase
from typing import Dict
from utils.getLogs import LOG
from setting import config_data

TAG = __name__
LANG_MAP = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese"
}


class ASRProvider(ASRProviderBase):
    def __init__(self, config: Dict):
        # self.url = config.get("url")
        self.mode = "stream"
        self.qwen3_asr_websocket = None
        self.params = config.get("params")
        
    async def initialize(self, websocket: WebSocket, conn: ConnectionObjectCustomAec3):
        try:
            # 对于 websockets >= 14.0，使用 additional_headers
            url = conn.global_config.get("asr_config").get("url").format(uid=conn.uid, apikey=conn.global_config.get("asr_config").get("apikey"))
            print(f"url is {url}")
            async with websockets.connect(
                url,
                additional_headers=self.params.get("headers")
            ) as qwen3_asr_websocket:
                start_msg = {
                    "vad_max_thre": 0.9,
                    "vad_min_thre": 0.65,
                    "silence_threshold_ms": 1500
                }
                await qwen3_asr_websocket.send(json.dumps(start_msg, ensure_ascii=False))
                self.qwen3_asr_websocket = qwen3_asr_websocket
                task_group =  asyncio.gather(
                    self.send_audio_data(websocket, conn),
                    self.receive_recognize_result(websocket, conn),)
                while conn.is_active:
                    await asyncio.sleep(0.05)
                await qwen3_asr_websocket.close()
                LOG(f"{TAG} 链接断开", "DEBUG")
        except WebSocketDisconnect:
            ...
    
    async def send_audio_data(self, websocket: WebSocket, conn: ConnectionObjectCustomAec3):
        try:
            while conn.is_active:
                if not conn.audio_chunk_queue.empty():
                    item = conn.audio_chunk_queue.get()
                    if isinstance(item, tuple):
                        pcm_frame, _ = item
                    else:
                        pcm_frame = item
                    await self.qwen3_asr_websocket.send(pcm_frame)
                    await asyncio.sleep(0.002)
                else:
                    await asyncio.sleep(0.002)
        except websockets.exceptions.ConnectionClosedOK:
            ...
    
    async def receive_recognize_result(self, websocket: WebSocket, conn: ConnectionObjectCustomAec3):
        try:
            while conn.is_active:
                data = await self.qwen3_asr_websocket.recv()
                LOG(f"{TAG} 接收到服务端数据：{data}", "DEBUG")
                if isinstance(data, str):
                    resp = json.loads(data)
                    if resp["type"] == "vad_start":
                        LOG(f"{TAG} 开始监听", "DEBUG")
                        conn.status = 1
                        await websocket.send_json({"type": "interrupt"})
                        await websocket.send_json({"type": "start_listening"})
                    elif resp["type"] == "chunk":
                        LOG(f"{TAG} 流式语音识别结果：{resp}", "DEBUG")
                        await websocket.send_json({
                                "type": "chunk",
                                "timestamp": None,
                                "text": resp["text"],
                                "language": "",
                                "latency_ms": None,
                                "chunk_count": None
                            })
                    elif resp["type"] == "vad_stop":
                        LOG(f"{TAG} 停止监听", "DEBUG")
                        conn.status = 0
                        await websocket.send_json({"type": "stop_listening"})
                    elif resp["type"] == "transcription":
                        conn.in_recognize = True
                        LOG(f"{TAG} 语音识别完成 {resp}", "DEBUG")
                        if resp["language"] in LANG_MAP:
                            lang_type = LANG_MAP[resp["language"]]
                        else:
                            lang_type = ""
                        # # 尝试过一遍热词
                        # _final_text = hotwords_module.correct(resp["transcript"])
                        # # 再过一遍文本替换
                        # final_text = replace_special_keyword(_final_text)
                        await websocket.send_json({
                                "type": "transcription",
                                "text": resp["text"],
                                "language": lang_type
                                })
                        if resp["text"]: conn.llm_queue.put(resp["text"])
                        conn.in_recognize = False
                await asyncio.sleep(0.003)
        except websockets.exceptions.ConnectionClosedOK:
            ...
    
    async def speech_to_text(self, file_path: str, conn):
        ...
