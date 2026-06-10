import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.work_order import Task
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal
from datetime import datetime


async def wo_save_one_task(**kwargs):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            new_task = Task(**kwargs)
            session.add(new_task)
    return 1


async def wo_update_save_one_task(**kwargs):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=kwargs["task_id"])
            )
            if task_info:
                task_info.title = kwargs.get("title")
                task_info.description = kwargs.get("description")
                task_info.owner_id = kwargs.get("owner_id")
                task_info.task_type = kwargs.get("task_type")
                task_info.assignee_ids = kwargs.get("assignee_ids")
                session.add(task_info)
                return 1
    return 0


async def wo_check_task_image(task_id: str, type: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=task_id)
            )
            if task_info:
                if type == "upload_start_task_image":
                    if task_info.photo_path:
                        return 1
                elif type == "upload_finish_task_image":
                    if task_info.completed_photo_path:
                        return 1
    return 0


async def wo_save_task_image(task_id: str, type: str, save_path: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=task_id)
            )
            if task_info:
                if type == "upload_start_task_image":
                    task_info.photo_path = save_path
                    session.add(task_info)
                    return 1
                elif type == "upload_finish_task_image":
                    task_info.completed_photo_path = save_path
                    task_info.status = 4
                    session.add(task_info)
                    return 1
    return 0


async def wo_update_task_status(task_id: str, status: int):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=task_id)
            )
            if task_info:
                task_info.status = status
                session.add(task_info)
                return 1
    return 0