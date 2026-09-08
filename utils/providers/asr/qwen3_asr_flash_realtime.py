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
        self.url = config.get("url")
        self.mode = "stream"
        self.aliyun_websocket = None
        self.params = config.get("params")
        
    async def initialize(self, websocket: WebSocket, conn: ConnectionObjectCustomAec3):
        try:
            # 对于 websockets >= 14.0，使用 additional_headers
            async with websockets.connect(
                self.url,
                additional_headers=self.params.get("headers")
            ) as aliyun_websocket:
                start_msg = {
                    "event_id": str(uuid.uuid4()),
                    "type": "session.update",
                    "session": {
                        "input_audio_format": "pcm",
                        "sample_rate": 16000,
                        "input_audio_transcription": {
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.9,
                            "silence_duration_ms": 1200
                        }
                    }
                }
                await aliyun_websocket.send(json.dumps(start_msg, ensure_ascii=False))
                _response = await aliyun_websocket.recv()
                response = json.loads(_response)
                LOG(f"{TAG} receive aliyun response {response}", "DEBUG")
                self.aliyun_websocket = aliyun_websocket
                task_group = None
                if response["type"] == "session.created":
                    task_group =  asyncio.gather(
                    self.send_audio_data(websocket, conn),
                    self.receive_recognize_result(websocket, conn),
                )
                else:
                    await aliyun_websocket.close()
                    raise ValueError(response)
                while conn.is_active:
                    await asyncio.sleep(0.05)
                await aliyun_websocket.close()
                LOG(f"{TAG} aliyun asr 链接断开", "DEBUG")
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
                    base64_pcm =  {
                        # "event_id": conn.event_id,
                        "event_id": str(uuid.uuid4()),
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm_frame).decode('utf-8')
                        }
                    await self.aliyun_websocket.send(json.dumps(base64_pcm))
                    await asyncio.sleep(0.005)
                else:
                    await asyncio.sleep(0.005)
        except websockets.exceptions.ConnectionClosedOK:
            ...
    
    async def receive_recognize_result(self, websocket: WebSocket, conn: ConnectionObjectCustomAec3):
        try:
            while conn.is_active:
                data = await self.aliyun_websocket.recv()
                LOG(f"{TAG} 接收到服务端数据：{data}", "DEBUG")
                if isinstance(data, str):
                    resp = json.loads(data)
                    if resp["type"] == "session.updated":
                        LOG(f"{TAG} aliyun 链接成功...", "DEBUG")
                    elif resp["type"] == "input_audio_buffer.speech_started":
                        LOG(f"{TAG} 开始监听", "DEBUG")
                        conn.status = 1
                        await websocket.send_json({"type": "interrupt"})
                        await websocket.send_json({"type": "start_listening"})
                    elif resp["type"] == "conversation.item.input_audio_transcription.text":
                        LOG(f"{TAG} 流式语音识别结果：{resp}", "DEBUG")
                        await websocket.send_json({
                                "type": "chunk",
                                "timestamp": None,
                                "text": resp["stash"],
                                "language": "",
                                "latency_ms": None,
                                "chunk_count": None
                            })
                    elif resp["type"] == "input_audio_buffer.committed":
                        LOG(f"{TAG} 停止监听", "DEBUG")
                        conn.status = 0
                        await websocket.send_json({"type": "stop_listening"})
                    elif resp["type"] == "conversation.item.input_audio_transcription.completed":
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
                                "text": resp["transcript"],
                                "language": lang_type
                            }
                        )
                        conn.llm_queue.put(resp["transcript"])
                        conn.in_recognize = False
                await asyncio.sleep(0.003)
        except websockets.exceptions.ConnectionClosedOK:
            ...
    
    async def speech_to_text(self, file_path: str, conn):
        ...
        
    async def close(self):
        await self.aliyun_websocket.close()
        LOG(f"aliyun asr 链接断开", "DEBUG")