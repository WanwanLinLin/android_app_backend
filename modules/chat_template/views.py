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
from mybatisPlus.chat_template_orm import (get_chat_template_list, add_one_chat_template, get_one_chat_template,
                                           update_one_chat_template, delete_one_chat_template)
from mybatisPlus.shelf_orm import off_shelf_preview, set_shelf_status
from mybatisPlus.tables.industrial_park import STATUS_ACTIVE, STATUS_OFF_SHELF
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from utils.auth import validate_accesskey
from utils.admin_auth import require_admin

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 资源池写操作（新增/更新/删除）一律仅 role=admin 可用，理由同 tts/views.py。

@router.post("/v1/chatTemplate/list", summary="获取对话模板列表", tags=["通用接口"],
             dependencies=[Depends(validate_accesskey)])
async def _list_chat_template():
    return GeneticResponse(data= await get_chat_template_list())


@router.post("/v1/chatTemplate/add", summary="添加对话模板", tags=["通用接口"])
async def _add_chat_template(info: schema.AddChatTemplateodel,
                             admin: dict = Depends(require_admin)):
    await add_one_chat_template(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/chatTemplate/get/{id}", summary="获取一个对话模板配置", tags=["通用接口"],
            dependencies=[Depends(validate_accesskey)])
async def _get_chat_template(id: int):
    data = await get_one_chat_template(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/chatTemplate/update/{id}", summary="更新对话模板", tags=["通用接口"])
async def _update_chat_template(id: int, info: schema.UpdateChatTemplateModel,
                                admin: dict = Depends(require_admin)):
    return await update_one_chat_template(id, **info.model_dump(exclude_none=True))


@router.post("/v1/chatTemplate/delete/{id}", summary="删除对话模板（软删除）", tags=["通用接口"])
async def _delete_chat_template(id: int, admin: dict = Depends(require_admin)):
    return await delete_one_chat_template(id)


# ===================== 上下架（仅管理员），语义同 tts/views.py =====================

@router.get("/v1/chatTemplate/offShelfPreview/{id}", summary="下架影响面预览（受影响租户）",
            tags=["通用接口"])
async def _ct_off_shelf_preview(id: int, admin: dict = Depends(require_admin)):
    return await off_shelf_preview("CHATTEMPLATE", id)


@router.post("/v1/chatTemplate/offShelf/{id}", summary="下架对话模板", tags=["通用接口"])
async def _ct_off_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("CHATTEMPLATE", id, STATUS_OFF_SHELF)


@router.post("/v1/chatTemplate/onShelf/{id}", summary="上架对话模板", tags=["通用接口"])
async def _ct_on_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_shelf_status("CHATTEMPLATE", id, STATUS_ACTIVE)
