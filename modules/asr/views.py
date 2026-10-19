import re
import io
import os
import struct
import time
import json
import uuid
import base64
import aiohttp
import asyncio
import aiofiles
from . import schema
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import APIRouter, status, WebSocket, WebSocketDisconnect, Depends, UploadFile, Form, File
from pydub import AudioSegment
from mybatisPlus.asr_orm import (add_one_asr, get_one_asr, get_asr_list,
                                 update_one_asr, delete_one_asr)
from mybatisPlus.shelf_orm import off_shelf_preview, set_shelf_status
from mybatisPlus.tables.industrial_park import STATUS_ACTIVE, STATUS_OFF_SHELF
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from utils.auth import validate_accesskey
from utils.admin_auth import require_admin, current_admin, is_admin

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 资源池写操作（新增/更新/删除）一律仅 role=admin 可用，理由同 tts/views.py。

@router.post("/v1/asr/list", summary="获取语音识别模型列表", tags=["通用接口"])
async def _list_asr(admin: dict = Depends(current_admin)):
    """admin 看全量（含已下架，便于重新上架）；普通用户只看在售资源。"""
    return GeneticResponse(data=await get_asr_list(only_active=not is_admin(admin)))


@router.post("/v1/asr/add", summary="添加语音识别模型", tags=["通用接口"])
async def _add_asr(info: schema.AddLLModel, admin: dict = Depends(require_admin)):
    await add_one_asr(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/asr/get/{id}", summary="获取一个语音识别模型配置", tags=["通用接口"],
            dependencies=[Depends(validate_accesskey)])
async def _get_asr(id: int):
    data = await get_one_asr(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/asr/update/{id}", summary="更新语音识别模型", tags=["通用接口"])
async def _update_asr(id: int, info: schema.UpdateLLModel,
                      admin: dict = Depends(require_admin)):
    return await update_one_asr(id, **info.model_dump(exclude_none=True))


@router.post("/v1/asr/delete/{id}", summary="删除语音识别模型（软删除）", tags=["通用接口"])
async def _delete_asr(id: int, admin: dict = Depends(require_admin)):
    return await delete_one_asr(id)


# ===================== 上下架（仅管理员），语义同 tts/views.py =====================

@router.get("/v1/asr/offShelfPreview/{id}", summary="下架影响面预览（受影响租户）",
            tags=["通用接口"])
async def _asr_off_shelf_preview(id: int, admin: dict = Depends(require_admin)):
    return await off_shelf_preview("ASR", id)


@router.post("/v1/asr/offShelf/{id}", summary="下架语音识别模型", tags=["通用接口"])
async def _asr_off_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("ASR", id, STATUS_OFF_SHELF)


@router.post("/v1/asr/onShelf/{id}", summary="上架语音识别模型", tags=["通用接口"])
async def _asr_on_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("ASR", id, STATUS_ACTIVE)
