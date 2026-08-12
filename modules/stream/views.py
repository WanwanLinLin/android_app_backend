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
import websockets

from utils.apierror import AccessKeyAuthError
from . import schema
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import APIRouter, status, WebSocket, WebSocketDisconnect, Depends, UploadFile, Form, File
from pydub import AudioSegment
from utils.common.schema import GeneticResponse
from utils.common.auth import OnewayEncryption, validate_stream_accesskey
from utils.core.webrtc_aec3.voice_handler import (ConnectionObjectCustomAec3, receive_audio_data, webrtc_aec3, send_audio_data,
                                                  recognize_asr_file, get_llm_result, get_tts_path_monitor, send_asr_chunk)
from mybatisPlus.user_orm import get_source_list, get_source_config, get_default_source_config, save_default_source_config
from utils.getLogs import LOG
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/stream/getSourceList", summary="获取用户拥有的资源列表", tags=["通用接口"],
             dependencies=[Depends(validate_stream_accesskey)])
async def _get_source_list(username: str):
    return GeneticResponse(data=await get_source_list(username))


# @router.post("/v1/stream/getSourceConfig", summary="获取用户当前使用的资源", tags=["通用接口"])
# async def _get_source_config():
#     return GeneticResponse(data=await get_source_config())


@router.post("/v1/stream/getDefaultSourceConfig", summary="获取用户当前使用的资源", tags=["通用接口"])
async def _get_default_source_config(username: str):
    return GeneticResponse(data=await get_default_source_config(username))


@router.post("/v1/stream/saveDefaultSourceConfig", summary="获取用户当前使用的资源", tags=["通用接口"])
async def _save_default_source_config(info: schema.SaveDefaultSourceConfig):
    await save_default_source_config(**info.model_dump())
    return GeneticResponse()


@router.websocket("/v1/stream/recognition")
async def websocket_endpoint(websocket: WebSocket, uid: str, token: str, timeStamp: str):
    await websocket.accept()
    if not OnewayEncryption().verify_token(timeStamp, token): raise AccessKeyAuthError
    prompt = await websocket.receive_json()
    LOG(f"start with client config: {prompt}", "DEBUG")
    conn = ConnectionObjectCustomAec3("manbaout", vad_max_thre=prompt.get("vad_max_thre", 0.9),
                                      vad_min_thre=prompt.get("vad_min_thre", 0.65), silence_threshold_ms=prompt.get("silence_threshold_ms", 1500))
    conn.pa.initAec(1, 16000, 16, 1, 16000, 16)
    conn.frv.init(
        config_data["MODEL_CONFIG"][0]["path"] + "firered_vad_packed_cache_stream.ncnn.param",
        config_data["MODEL_CONFIG"][0]["path"] + "firered_vad_packed_cache_stream.ncnn.bin",
        config_data["MODEL_CONFIG"][0]["path"] + "cmvn_means_stream.bin",
        config_data["MODEL_CONFIG"][0]["path"] + "cmvn_istd_stream.bin",
        16000, 10, 25, 0.9,
    )
    all_configs = await get_source_config(llm_id=prompt.get("source_config", {}).get("model_id", None),
                                          tts_id=prompt.get("source_config", {}).get("tts_id", None),
                                          asr_id=prompt.get("source_config", {}).get("asr_id", None))
    llm_config = all_configs.get("llm_config")
    tts_config = all_configs.get("tts_config")
    asr_config = all_configs.get("asr_config")
    conn.global_config["llm_config"] = llm_config
    conn.global_config["tts_config"] = tts_config
    conn.global_config["asr_config"] = asr_config
    asr_lib_name = f"utils.providers.asr.{asr_config.get('type')}"
    tts_lib_name = f"utils.providers.tts.{tts_config.get('tag')}"
    llm_lib_name = f"utils.providers.llm.{llm_config.get('type')}"
    conn.asr_engine = importlib.import_module(asr_lib_name).ASRProvider(asr_config)
    conn.tts_engine = importlib.import_module(tts_lib_name).TTSProvider(tts_config)
    conn.llm_engine = importlib.import_module(llm_lib_name).LLMProvider(llm_config)
    conn.chunk_asr_client = await websockets.connect(asr_config.get("params").get("stream_asr_url"))
    # conn.chunk_asr_client = await websockets.connect("ws://192.168.3.36:18113/v1/stream/chunk")
    try:
        await asyncio.gather(
            receive_audio_data(websocket, conn),
            webrtc_aec3(websocket, conn),
            send_audio_data(websocket, conn),
            recognize_asr_file(websocket, conn),
            get_llm_result(websocket, conn),
            get_tts_path_monitor(websocket, conn),
            send_asr_chunk(websocket, conn),
        )
    except WebSocketDisconnect as e:
        conn.is_active = False
        conn.pa = None
        conn.frv = None
        await conn.chunk_asr_client.close()
        await asyncio.sleep(1)  # 等待资源释放
        conn = None
        # print(f"manba out {e}")
    
    # except Exception as e:
    #     conn.pa = None
    #     conn.frv = None
    #     await conn.chunk_asr_client.close()
    #     conn = None
    #     LOG(f"客户端连接异常断开: {e}", "DEBUG")