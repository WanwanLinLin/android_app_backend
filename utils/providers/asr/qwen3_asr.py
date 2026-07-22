import os
import base64
import hashlib
import hmac
import json
import time
import aiohttp
import numpy as np
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from utils.providers.asr.base import ASRProviderBase
from typing import Dict

TAG = __name__


class ASRProvider(ASRProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
    
    async def speech_to_text(self, file_path: str, conn):
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url,
                                    json={
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "audio_url",
                                    "audio_url": {
                                        "url": f"file://{file_path}"
                                    }
                                }
                            ]
                        }
                    ]
                }) as _resp:
                resp = await _resp.json()
                print("resp is ", resp)
                text = resp["choices"][0]["message"]["content"]
                # 1. 分割出语种部分
                lang_part = text.split("<asr_text>")[0]  # 先按标签分割，取前面部分
                language = lang_part.replace("language ", "").strip()  # 去掉前缀，得到语种
                # 2. 分割出识别文本
                result = text.split("<asr_text>")[1]  # 取标签后面的内容
                os.remove(file_path)
                return {"code": 200, "data": result, "language": language}