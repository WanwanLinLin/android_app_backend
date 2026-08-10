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
from mybatisPlus.llm_orm import (add_one_llm, get_one_llm, get_llm_list)
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/llm/list", summary="获取大模型列表", tags=["通用接口"])
async def _add_llm(info: schema.AddLLModel):
    return GeneticResponse(data= await get_llm_list())


@router.post("/v1/llm/add", summary="添加大模型/agent", tags=["通用接口"])
async def _add_llm(info: schema.AddLLModel):
    await add_one_llm(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/llm/get/{id}", summary="获取一个大模型配置", tags=["通用接口"])
async def _get_llm(id: int):
    data = await get_one_llm(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")
