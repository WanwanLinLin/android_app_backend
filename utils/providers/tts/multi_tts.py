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


# 语种别名归一化：ASR/LLM 写入的可能是全称（Chinese/English/...），
# additional_param 配置的键可能是缩写（zh/en/...），两边都归一到缩写再匹配
LANG_ALIAS = {
    "zh": "zh", "chinese": "zh", "zh-cn": "zh", "zh_cn": "zh",
    "yue": "yue", "cantonese": "yue", "zh-hk": "yue", "zh_hk": "yue",
    "en": "en", "english": "en", "en-us": "en", "en_us": "en",
    "ja": "ja", "japanese": "ja", "ja-jp": "ja", "ja_jp": "ja",
}


def normalize_lang(value):
    """把语种标识归一为缩写键（zh/en/ja/yue），未知返回小写原值。"""
    v = str(value or "").strip().lower()
    return LANG_ALIAS.get(v, v)


class TTSProvider(TTSProviderBase):
    def __init__(self, config: Dict):
        self.url = config.get("url")
        self.voice = config.get("voice")
        # 参数键 2026-10-22 起统一为 params（原 additional_param）；回退读旧键兼容外部配置
        self.additional_param = config.get("params") or config.get("additional_param") or {}

    def match_language(self, language, param: Dict):
        """在 additional_param 中查找 language 对应的键：先精确命中，再按别名归一匹配。"""
        if language and language in param:
            return language
        norm = normalize_lang(language)
        if norm:
            for k in param:
                if k == "default":
                    continue
                if normalize_lang(k) == norm:
                    return k
        return None

    async def text_to_speak(self, text, conn):
        nums = 0
        for i in range(5):
            nums += 1
            start_time = time.perf_counter()
            _save_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".pcm"
            save_path = config_data["CACHE"]["tts"] + "16k_" + str(uuid.uuid4()) + ".pcm"
            if not text: return save_path
            # 语种优先级由写入顺序保证：每轮 ASR 先写 conn.current_language，
            # 大模型（如 ljz_workflow meta 事件）随后覆盖 → 合成时 LLM 语种优先生效
            lang_key = self.match_language(conn.current_language, self.additional_param)
            if lang_key is None and "default" not in self.additional_param:
                LOG(f"error: 语种 {conn.current_language!r} 未配置且无 default 兜底，本句跳过合成：{text}", "WARNING")
                return None
            tts_id = self.additional_param[lang_key if lang_key else "default"]
            try:
                tts_config = await get_one_voice(tts_id)
                LOG(f"当前语种：{conn.current_language} | 命中键：{lang_key or 'default'} | 使用的tts: {tts_config}", "DEBUG")
                tts_lib_name = f"utils.providers.tts.{tts_config.get('tag')}"
                tts_engine = importlib.import_module(tts_lib_name).TTSProvider(tts_config)
                return await tts_engine.text_to_speak(text, conn)
            except Exception as e:
                LOG(f"error: 合成 {text} 报错：{e}。重试第 {nums} 次。", "DEBUG")
                # return 0
                continue