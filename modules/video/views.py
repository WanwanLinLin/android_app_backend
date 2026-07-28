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
from pydub import AudioSegment
from utils.common.schema import GeneticResponse
from utils.common.auth import validate_stream_accesskey
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import APIRouter, Request, Response, status, WebSocket, WebSocketDisconnect, Depends, UploadFile, Form, File
from setting import *

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.get("/v1/video/play/{name}/{action}/{fileName}", summary="播放数字人动作", tags=["通用接口"])
async def voice_list(request: Request, response: Response, name: str, action: str, fileName: str):
    """
    http://113.108.106.173:8852/v1/video/play/cutegirl/speaking/video.m3u8
    http://113.108.106.173:8852/v1/video/play/cutegirl/stanby/video.m3u8
    """
    if action == "stanby":
        base_path = os.path.join(CURRENT_PATH, "static", "m3u8", "cutegirl", "stanby", fileName)
    else:
        base_path = os.path.join(CURRENT_PATH, "static", "m3u8", "cutegirl", "speaking", fileName)
    return FileResponse(base_path, filename=fileName)
