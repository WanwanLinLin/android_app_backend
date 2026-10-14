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
from mybatisPlus.tts_orm import (get_voice_list, add_one_voice, get_one_voice,
                                 update_one_voice, delete_one_voice)
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/tts/list", summary="受支持的音色列表", tags=["通用接口"])
async def voice_list():
    return GeneticResponse(data=await get_voice_list())


@router.post("/v1/tts/add", summary="增加一个音色", tags=["通用接口"])
async def add_voice(info: schema.AddVoiceModel):
    await add_one_voice(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/tts/get/{id}", summary="获取一个音色详情", tags=["通用接口"], dependencies=[Depends(validate_stream_accesskey)])
async def _get_one_voice(id: int):
    data = await get_one_voice(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/tts/update/{id}", summary="更新音色", tags=["通用接口"])
async def _update_voice(id: int, info: schema.UpdateVoiceModel):
    return await update_one_voice(id, **info.model_dump(exclude_none=True))


@router.post("/v1/tts/delete/{id}", summary="删除音色（软删除）", tags=["通用接口"])
async def _delete_voice(id: int):
    return await delete_one_voice(id)