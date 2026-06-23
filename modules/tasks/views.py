# -*- coding：utf-8 -*-
from datetime import datetime
import os
import time
import uuid
import aiohttp
import asyncio

from modules.agent.handle_task import receive_task_agent
from . import schema
from fastapi import APIRouter, File, Form, UploadFile, status
from utils.common.schema import GeneticResponse
from mybatisPlus.task_orm import create_task, update_task, save_task_image, get_task_info_by_id
from mybatisPlus.work_order_task_orm import wo_save_task_image, wo_save_one_task, wo_get_task_info_by_id
from utils.randomString import create_numbering
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/task/create")
async def _create_task(info: schema.CreateOrConfirmTaskModel):
    # 创建任务
    topic = f"task/{str(uuid.uuid4())}"
    task_id = f"{str(int(time.time()))}_{create_numbering(10)}"
    # 创建一条任务记录
    await create_task(topic=topic, task_id=task_id, device_id=info.device_id,
                      location=info.location, event_description=info.event_description)
    await wo_save_one_task(task_id=task_id, title="")
    asyncio.create_task(receive_task_agent(topic, task_id, info.event_description, info.location, info.device_id))
    return GeneticResponse(data={
        # "topic": topic,
        "task_id": task_id,
    })
    

@router.post("/v1/task/uplodaImage")
async def _upload_image(
                    task_id: str = Form(...),
                    type: str = Form(...),
                    file: UploadFile = File(..., max_size=5*1024*1024)):
    """
    上传图片最大为50M
    """
    if type not in ["upload_start_task_image", "upload_finish_task_image"]:
        return GeneticResponse(code=400, msg="不支持的上传文件类型")
    filename = f"{create_numbering(10)}_{str(datetime.strftime(datetime.now(), '%Y-%m-%d-%H-%M-%S'))}_{file.filename}"
    file_path = os.path.join(config_data["CACHE"]["image"], filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    db_save_path = config_data["SERVICES"][1]["image_base_url"] + filename
    if not await wo_save_task_image(task_id, type, db_save_path):
        return GeneticResponse(code=400, msg="任务不存在!")
    if not await save_task_image(task_id, type, db_save_path):
        return GeneticResponse(code=400, msg="任务不存在!")
    return GeneticResponse()


@router.post("/v1/task/detail")
async def _get_task_detail(info: schema.GetTaskDetail):
    # 创建任务
    i = await get_task_info_by_id(info.task_id)
    if not i: return GeneticResponse(code=400, msg="任务不存在。")
    j = i.model_dump()
    z = await wo_get_task_info_by_id(info.task_id)
    j.update(z)
    return GeneticResponse(data=j)