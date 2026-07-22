import re
import io
import os
import sys
import struct
import time
import json
import uuid
import base64
import aiohttp
import asyncio
import aiofiles
import importlib
from . import schema
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import APIRouter, status, WebSocket, WebSocketDisconnect, Depends, UploadFile, Form, File
from pydub import AudioSegment
from mybatisPlus.tts_orm import (get_voice_list, add_one_voice, get_one_voice)
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from utils.core.webrtc_aec3.voice_handler import (ConnectionObjectCustomAec3, receive_audio_data, webrtc_aec3, send_audio_data,
                                                  recognize_asr_file, get_llm_result, get_tts_path_monitor)
from utils.getLogs import LOG
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.websocket("/v1/stream/recognition")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    conn = ConnectionObjectCustomAec3("manbaout", silence_threshold_ms=1500)
    conn.pa.initAec(1, 16000, 16, 1, 16000, 16)
    conn.frv.init(
        config_data["MODEL_CONFIG"][0]["path"] + "firered_vad_packed_cache_stream.ncnn.param",
        config_data["MODEL_CONFIG"][0]["path"] + "firered_vad_packed_cache_stream.ncnn.bin",
        config_data["MODEL_CONFIG"][0]["path"] + "cmvn_means_stream.bin",
        config_data["MODEL_CONFIG"][0]["path"] + "cmvn_istd_stream.bin",
        16000, 10, 25, 0.9,
    )
    llm_config = {
        "model_name": "glm_47_flash",
        "base_url": "http://192.168.1.52:18831/v1",
        "url": "http://192.168.1.52:18831/v1/chat/completions",
        "api_key": "123",
    }
    tts_config = {
        "url": "http://192.168.1.52:18852/v1/audio/speech",
        "voice": "zh_female_zhixingnvsheng_mars_bigtts",
        "apikey": "12345"
    }
    asr_config = {
        "url": "http://192.168.1.52:18832/v1/chat/completions",
        "apikey": "12345",
    }
    asr_lib_name = f"utils.providers.asr.qwen3_asr"
    tts_lib_name = f"utils.providers.tts.CosyVoice"
    llm_lib_name = f"utils.providers.llm.openai.openai"
    conn.asr_engine = importlib.import_module(asr_lib_name).ASRProvider(asr_config)
    conn.tts_engine = importlib.import_module(tts_lib_name).TTSProvider(tts_config)
    conn.llm_engine = importlib.import_module(llm_lib_name).LLMProvider(llm_config)
    
    try:
        await asyncio.gather(
            receive_audio_data(websocket, conn),
            webrtc_aec3(websocket, conn),
            send_audio_data(websocket, conn),
            recognize_asr_file(websocket, conn),
            get_llm_result(websocket, conn),
            get_tts_path_monitor(websocket, conn),
        )
    except WebSocketDisconnect as e:
        conn.pa = None
        conn.frv = None
        conn = None
        print(f"manba out {e}")
    
    except RecursionError as e:
        conn.pa = None
        conn.frv = None
        conn = None
        LOG(f"客户端连接异常断开: {e}", "DEBUG")