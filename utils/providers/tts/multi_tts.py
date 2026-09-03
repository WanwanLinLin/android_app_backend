import importlib
import re
import sys
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
from mybatisPlus.tts_orm import get_one_voice


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        self.additional_param = config.get("additional_param", {})
    
    async def text_to_speak(self, text, conn):
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".pcm"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".pcm"
            if not text: return save_path
            try:
                if conn.current_language in self.additional_param:
                    tts_config = await get_one_voice(self.additional_param[conn.current_language])
                else:
                    tts_config = await get_one_voice(self.additional_param["default"])
                LOG(f"当前语种：{conn.current_language} | 使用的tts: {tts_config}", "DEBUG")
                tts_lib_name = f"utils.providers.tts.{tts_config.get('tag')}"
                tts_engine = importlib.import_module(tts_lib_name).TTSProvider(tts_config)
                return await tts_engine.text_to_speak(text, conn)
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue