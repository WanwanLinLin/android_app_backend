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
from utils.getLogs import LOG

TAG = __name__


class ASRProvider(ASRProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
    
    async def speech_to_text(self, file_path: str, conn):
        async with aiohttp.ClientSession() as session:
            # 文件在 with 块内打开，请求完成后自动关闭
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='audio.wav', content_type='audio/wav')
                # data.add_field('hotwords', hotwords)

                async with session.post(self.url, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        LOG(f"{__name__} 识别结果: {result}", "DEBUG")
                    else:
                        error_text = await response.text()
                        LOG(f"{__name__} 请求失败，状态码: {response.status}, 错误: {error_text}", "DEBUG")
                        return {"code": 400, "data": error_text, "language": ""}
                os.remove(file_path)
                return {"code": 200, "data": result["data"], "language": ""}