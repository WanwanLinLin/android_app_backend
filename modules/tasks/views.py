# -*- coding：utf-8 -*-
import time
import uuid
import aiohttp
import asyncio

from modules.agent.handle_task import receive_task_agent
from . import schema
from fastapi import APIRouter, status
from utils.common.schema import GeneticResponse
from mybatisPlus.task_orm import create_task
from utils.randomString import create_numbering

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/task/create")
async def _create_task(info: schema.CreateOrConfirmTaskModel):
    # 创建任务
    topic = f"task/{str(uuid.uuid4())}"
    task_id = f"{str(int(time.time()))}_{create_numbering(10)}"
    # 创建一条任务记录
    await create_task(topic=topic, task_id=task_id, device_id=info.device_id,
                      location=info.location, event_description=info.event_description)
    asyncio.create_task(receive_task_agent(topic, task_id, info.event_description, info.location, info.device_id))
    return GeneticResponse(data={
        # "topic": topic,
        "task_id": task_id,
    })
