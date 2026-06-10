# -*- coding：utf-8 -*-
import time
import uuid
import aiohttp
import asyncio

from modules.agent.handle_task import receive_task_agent
from mybatisPlus.device_orm import update_location
from . import schema
from fastapi import APIRouter, status
from utils.common.schema import GeneticResponse
from mybatisPlus.task_orm import  create_task
from mybatisPlus.engineer_orm import list_all_engineer
from utils.randomString import create_numbering

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/device/updateLocation")
async def _update_location(info: schema.UpdateLocationModel):
    return await update_location(info.device_id, info.location)