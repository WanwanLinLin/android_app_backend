import os
import base64
import hashlib
import hmac
import json
import time
import base64
import aiohttp
import numpy as np
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from utils.providers.asr.base import ASRProviderBase
from typing import Dict
from utils.getLogs import LOG
from setting import config_data

TAG = __name__


class ASRProvider(ASRProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
    
    async def speech_to_text(self, file_path: str, conn):
        if config_data["SERVICES"][0]["host_ip"] in self.url:
            input_data = {
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
                }
        else:
            with open(file_path, "rb") as f:
                audio_data = f.read()
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            input_data = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "audio_url",
                                    "audio_url": {
                                        "url": f"data:audio/wav;base64,{base64_audio}"
                                    }
                                }
                            ]
                        }
                    ]
                }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url,
                                    json=input_data) as _resp:
                resp = await _resp.json()
                LOG(f"{TAG} resp is {resp}", "DEBUG")
                text = resp["choices"][0]["message"]["content"]
                # 1. 分割出语种部分
                lang_part = text.split("<asr_text>")[0]  # 先按标签分割，取前面部分
                language = lang_part.replace("language ", "").strip()  # 去掉前缀，得到语种
                # 2. 分割出识别文本
                result = text.split("<asr_text>")[1]  # 取标签后面的内容
                os.remove(file_path)
                return {"code": 200, "data": result, "language": language}