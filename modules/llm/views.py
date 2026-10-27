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
from mybatisPlus.agent_orm import (add_one_agent, get_one_agent, get_agent_list,
                                   update_one_agent, delete_one_agent)
from mybatisPlus.shelf_orm import off_shelf_preview, set_shelf_status
from mybatisPlus.tables.industrial_park import STATUS_ACTIVE, STATUS_OFF_SHELF
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from utils.auth import validate_accesskey
from utils.admin_auth import require_admin, current_admin, is_admin
from utils.secret_mask import mask_secrets

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 资源池写操作（新增/更新/删除）一律仅 role=admin 可用，理由同 tts/views.py。

@router.post("/v1/agent/list", summary="获取大模型列表（旧资源池，仅管理员）", tags=["通用接口"])
async def _list_agents(admin: dict = Depends(require_admin)):
    """旧 Factories 资源池为遗留通道，理由同 asr/views.py。"""
    return GeneticResponse(data=mask_secrets(await get_agent_list(only_active=False)))


@router.post("/v1/agent/add", summary="添加大模型/agent", tags=["通用接口"])
async def _add_agent(info: schema.AddLLModel, admin: dict = Depends(require_admin)):
    await add_one_agent(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/agent/get/{id}", summary="获取一个大模型配置", tags=["通用接口"],
            dependencies=[Depends(validate_accesskey)])
async def _get_agent(id: int):
    data = await get_one_agent(id)
    if data: return GeneticResponse(data=mask_secrets(data))
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/agent/update/{id}", summary="更新大模型", tags=["通用接口"])
async def _update_agent(id: int, info: schema.UpdateLLModel,
                        admin: dict = Depends(require_admin)):
    return await update_one_agent(id, **info.model_dump(exclude_none=True))


@router.post("/v1/agent/delete/{id}", summary="删除大模型（软删除）", tags=["通用接口"])
async def _delete_agent(id: int, admin: dict = Depends(require_admin)):
    return await delete_one_agent(id)


# ===================== 上下架（仅管理员），语义同 tts/views.py =====================

@router.get("/v1/agent/offShelfPreview/{id}", summary="下架影响面预览（受影响租户）",
            tags=["通用接口"])
async def _agent_off_shelf_preview(id: int, admin: dict = Depends(require_admin)):
    return await off_shelf_preview("LLM", id)


@router.post("/v1/agent/offShelf/{id}", summary="下架大模型", tags=["通用接口"])
async def _agent_off_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("LLM", id, STATUS_OFF_SHELF)


@router.post("/v1/agent/onShelf/{id}", summary="上架大模型", tags=["通用接口"])
async def _agent_on_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("LLM", id, STATUS_ACTIVE)
