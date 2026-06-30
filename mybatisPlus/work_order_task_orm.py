import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.work_order import Device2UserInfo, Task
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal
from datetime import datetime


class _TaskDetail(BaseModel):
    title: Union[str, None]
    description: Union[str, None]
    assignee_ids: Union[str, List, None]
    task_type: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("assignee_ids")
    def get_assignee_ids(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)


class _TaskDetail2(BaseModel):
    task_id: Union[str, None] 
    title: Union[str, None]
    task_type: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


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


async def wo_get_task_info_by_id(task_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=task_id)
            )
            if task_info:
                return _TaskDetail.model_validate(task_info).model_dump()
    return None


async def wo_get_task_list_by_device_id(device_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            # 找到工程师id:
            engineer_info = await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
            )
            if not engineer_info: return None
            engineer_id = engineer_info.engineer_id
            task_ids = []
            task_info = await session.scalars(
                select(Task).filter(Task.status != -1, Task.status != 4)
                # select(Task).filter(Task.status != -1)
            )
            for t in task_info:
                if t.assignee_ids:
                    if engineer_id in json.loads(t.assignee_ids, strict=False):
                        task_ids.append(t.task_id)
            return task_ids
    return None


async def wo_get_task_list_by_device_id_2(device_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            # 找到工程师id:
            engineer_info = await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
            )
            if not engineer_info: return None
            engineer_id = engineer_info.engineer_id
            task_list = []
            task_info = await session.scalars(
                select(Task).filter(Task.status != -1, Task.status != 4)
                # select(Task).filter(Task.status != -1)
            )
            for t in task_info:
                if t.assignee_ids:
                    if engineer_id in json.loads(t.assignee_ids, strict=False):
                        task_list.append(_TaskDetail2.model_validate(t).model_dump())
            return task_list
    return None


async def wo_get_current_status(task_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(Task).filter_by(task_id=task_id)
            )
            return task_info.status
    return -1