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
from mybatisPlus.figure_orm import (get_figure_list, add_one_figure, get_one_figure, get_user_figure_list)
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from setting import CURRENT_PATH

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/figure/list", summary="静态资源列表", tags=["通用接口"])
async def figure_list():
    return GeneticResponse(data=await get_figure_list())


@router.post("/v1/figure/add", summary="增加一个静态资源", tags=["通用接口"])
async def add_figure(info: schema.AddFigureModel):
    await add_one_figure(**info.model_dump())
    return GeneticResponse()


@router.get("/v1/figure/get/{id}", summary="获取一个静态资源详情", tags=["通用接口"], dependencies=[Depends(validate_stream_accesskey)])
async def _get_one_figure(id: int):
    data = await get_one_figure(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/figure/user/list", summary="静态资源列表", tags=["通用接口"])
async def figure_list(username: str):
    return GeneticResponse(data=await get_user_figure_list(username))


@router.get("/v1/figure/download/{type}/{filename}", dependencies=[Depends(validate_stream_accesskey)])
async def download_large_file(type: str, filename: str):
    def iterfile(file_path: str):
        with open(file_path, mode="rb") as file_like:
            yield from file_like  # 每次读取一块并产出
    file_path = os.path.join(CURRENT_PATH, "static", type, filename)
    if not os.path.exists(file_path): return GeneticResponse(code=400, msg="source not exist")
    file_size = os.path.getsize(file_path)
    # 同样需要添加文件存在性等检查
    return StreamingResponse(
        iterfile(file_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}",
                  "Content-Length": str(file_size)}
    )