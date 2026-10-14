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
from fastapi import APIRouter, status, WebSocket, WebSocketDisconnect, Depends, Query, UploadFile, Form, File
from pydub import AudioSegment
from utils.common.schema import GeneticResponse
from utils.common.auth import OnewayEncryption, validate_stream_accesskey
from utils.core.webrtc_aec3.voice_handler import (ConnectionObjectCustomAec3)
from utils.common.enumTaskType import WebsocketServerEvent
from mybatisPlus.tenant_orm import (get_source_list, get_source_config,
                                    get_default_source_config, save_default_source_config)
from mybatisPlus.agent_orm import manage_agent_session
from utils.getLogs import LOG
from setting import config_data, vad_model_paths

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/stream/getSourceList", summary="获取租户拥有的资源列表", tags=["通用接口"],
             dependencies=[Depends(validate_stream_accesskey)])
async def _get_source_list(tenantname: str = Query(default=None), username: str = Query(default=None)):
    """业务归属已切换为 Tenant。

    终端旧版本仍以 username 传租户名，故二者皆接受，优先 tenantname。
    """
    return GeneticResponse(data=await get_source_list(tenantname or username))


# @router.post("/v1/stream/getSourceConfig", summary="获取租户当前使用的资源", tags=["通用接口"])
# async def _get_source_config():
#     return GeneticResponse(data=await get_source_config())


@router.post("/v1/stream/getDefaultSourceConfig", summary="获取租户当前使用的资源", tags=["通用接口"])
async def _get_default_source_config(tenantname: str = Query(default=None), username: str = Query(default=None)):
    return GeneticResponse(data=await get_default_source_config(tenantname or username))


@router.post("/v1/stream/saveDefaultSourceConfig", summary="保存租户默认资源", tags=["通用接口"])
async def _save_default_source_config(info: schema.SaveDefaultSourceConfig):
    await save_default_source_config(tenantname=info.tenantname or info.username,
                                     llm_id=info.llm_id, tts_id=info.tts_id, asr_id=info.asr_id)
    return GeneticResponse()


@router.websocket("/v1/stream/recognition")
async def websocket_endpoint(websocket: WebSocket, uid: str, token: str, timeStamp: str):
    """uid 为终端上报的业务身份标识，即 Tenant.tenantname。"""
    await websocket.accept()
    if not OnewayEncryption().verify_token(timeStamp, token): raise AccessKeyAuthError
    prompt = await websocket.receive_json()
    LOG(f"start with client config: {prompt}", "DEBUG")
    start_time = time.perf_counter()
    conn = ConnectionObjectCustomAec3("manbaout", vad_max_thre=prompt.get("vad_max_thre", 0.9),
                                      vad_min_thre=prompt.get("vad_min_thre", 0.65), silence_threshold_ms=prompt.get("silence_threshold_ms", 1500))
    # conn.pa.initAec(1, 16000, 16, 1, 16000, 16)
    conn.frv.init(
        *vad_model_paths(config_data["MODEL_CONFIG"][0]["path"]),
        16000, 10, 25, 0.9,
    )
    conn.chat_mode = prompt.get("prompt","aec")
    all_configs = await get_source_config(llm_id=prompt.get("source_config", {}).get("model_id", None),
                                          tts_id=prompt.get("source_config", {}).get("tts_id", None),
                                          asr_id=prompt.get("source_config", {}).get("asr_id", None),
                                          uid=uid)
    llm_config = all_configs.get("llm_config")
    tts_config = all_configs.get("tts_config")
    asr_config = all_configs.get("asr_config")
    chat_template_config = all_configs.get("chat_template_config")
    conn.global_config["llm_config"] = llm_config
    conn.global_config["tts_config"] = tts_config
    conn.global_config["asr_config"] = asr_config
    asr_lib_name = f"utils.providers.asr.{asr_config.get('type')}"
    tts_lib_name = f"utils.providers.tts.{tts_config.get('tag')}"
    llm_lib_name = f"utils.providers.llm.{llm_config.get('type')}"
    conn.asr_engine = importlib.import_module(asr_lib_name).ASRProvider(asr_config)
    conn.tts_engine = importlib.import_module(tts_lib_name).TTSProvider(tts_config)
    conn.llm_engine = importlib.import_module(llm_lib_name).LLMProvider(llm_config)
    chat_template_engine = importlib.import_module(chat_template_config.get("module_path"))
    LOG(f"Init base config total cost {time.perf_counter() - start_time} seconds", "DEBUG")
    # 向终端发送握手事件：
    await websocket.send_json(
        {"type": WebsocketServerEvent.SESSION_CREATE.value,
         "session_id": conn.session_id})
    
    conn.executor.submit(asyncio.run_coroutine_threadsafe, manage_agent_session(type="create", session_id=conn.session_id,
                                                           agent_id=llm_config.get("id"), asr_id=asr_config.get("id"),
                                                           tts_id=tts_config.get("id"), tenant_id=uid), conn.loop)

    # server_vad模式
    try:
        await asyncio.gather(
            # conn.asr_engine.initialize(websocket, conn),
            chat_template_engine.receive_audio_data(websocket, conn),
            chat_template_engine.send_audio_data(websocket, conn),
            chat_template_engine.agent_process_monitor(websocket, conn),
            chat_template_engine.tts_process_monitor(websocket, conn),
            chat_template_engine.asr_process_monitor(websocket, conn),
        )
    except WebSocketDisconnect:
        LOG(f"客户端连接断开", "DEBUG")
    except Exception as e:
        LOG(f"客户端连接异常断开: {e}", "DEBUG")
    finally:
        conn.executor.submit(asyncio.run_coroutine_threadsafe, manage_agent_session(type="update", session_id=conn.session_id,
                                                           dialogue_history=conn.dialogue_history), conn.loop)
        conn.is_active = False
        conn.pa = None
        conn.frv = None
        # await conn.chunk_asr_client.close()
        # await asyncio.sleep(2.5)
        # conn = None