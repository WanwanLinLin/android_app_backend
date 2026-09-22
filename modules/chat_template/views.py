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
from mybatisPlus.template_orm import (get_chat_template_list, add_one_chat_template, get_one_chat_template)
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/chatTemplate/list", summary="获取对话模板列表", tags=["通用接口"])
async def _list_chat_template():
    return GeneticResponse(data= await get_chat_template_list())


@router.post("/v1/chatTemplate/add", summary="添加对话模板", tags=["通用接口"])
async def _add_chat_template(info: schema.AddChatTemplateodel):
    await add_one_chat_template(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/chatTemplate/get/{id}", summary="获取一个对话模板配置", tags=["通用接口"])
async def _get_chat_template(id: int):
    data = await get_one_chat_template(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")
