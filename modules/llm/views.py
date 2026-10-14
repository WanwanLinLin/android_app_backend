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
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/agent/list", summary="获取大模型列表", tags=["通用接口"])
async def _list_agents():
    return GeneticResponse(data= await get_agent_list())


@router.post("/v1/agent/add", summary="添加大模型/agent", tags=["通用接口"])
async def _add_agent(info: schema.AddLLModel):
    await add_one_agent(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/agent/get/{id}", summary="获取一个大模型配置", tags=["通用接口"])
async def _get_agent(id: int):
    data = await get_one_agent(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/agent/update/{id}", summary="更新大模型", tags=["通用接口"])
async def _update_agent(id: int, info: schema.UpdateLLModel):
    return await update_one_agent(id, **info.model_dump(exclude_none=True))


@router.post("/v1/agent/delete/{id}", summary="删除大模型（软删除）", tags=["通用接口"])
async def _delete_agent(id: int):
    return await delete_one_agent(id)
