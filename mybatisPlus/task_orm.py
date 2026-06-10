import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import Device2UserInfo, HandleTaskRecord, EngineerInfo
from .tables.sqlcli import AsyncSessionLocal
from datetime import datetime


class ListEngineers(BaseModel):
    id: Union[int, None]
    name: Union[str, None]
    job: Union[str, None]
    phone_number: Union[str, None]
    create_time: Union[str, None]
    update_time: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        

class TaskDetail(BaseModel):
    id: Union[int, None]
    topic: Union[str, None]
    device_id: Union[str, None]
    task_id: Union[str, None]
    status: Union[int, None]
    exclude_engineer_id_list: Union[str, List, None]
    engineer_id: Union[int, None]
    report_engineer_id: Union[int, None]
    create_time: Union[str, None]
    update_time: Union[str, None]
    photo_path: Union[str, None]
    location: Union[str, None]
    completed_photo_path: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("exclude_engineer_id_list")
    def get_exclude_engineer_id_list(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)


async def create_task(**kwargs):
    kwargs["create_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    kwargs["update_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_task = HandleTaskRecord(**kwargs)
            session.add(new_task)
    return GeneticResponse()


async def update_task(task_id: str, mode: int = 0, **kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(HandleTaskRecord).filter_by(task_id=task_id)
            )
            if mode == 0:       # create_task 阶段
                if task_info:
                    task_info.solution = kwargs["solution"]
                    task_info.engineer_id = kwargs["engineer_id"]
                    task_info.update_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
                    task_info.report_engineer_id = kwargs["report_engineer_id"]
                    session.add(task_info)
            elif mode == 1:     # ack_task 阶段
                if not kwargs["ack"]:
                    if task_info.exclude_engineer_id_list:
                        task_info.exclude_engineer_id_list = json.dumps(json.loads(task_info.exclude_engineer_id_list).append(kwargs["engineer_id"]))
                    else:
                        task_info.exclude_engineer_id_list = json.dumps([kwargs["engineer_id"]])
                    session.add(task_info)
                    
                else:
                    task_info.engineer_id = kwargs["engineer_id"]
                    task_info.status = 1
                    session.add(task_info)
            elif mode == 2:
                task_info.status = kwargs["status"]
                task_info.update_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
                session.add(task_info)
            elif mode == 3:
                task_info.update_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
                session.add(task_info)
            else:
                task_info.status = -1
                task_info.solution = kwargs["solution"]
                task_info.report_engineer_id = kwargs["report_engineer_id"]
                task_info.update_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
                session.add(task_info)
    return GeneticResponse()


async def confirm_task(task_id: str, ack: bool):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(HandleTaskRecord).filter_by(task_id=task_id)
            )
            if task_info:
                task_info.ack = ack
                task_info.status = 1 if ack else 3
                session.add(task_info)
    return GeneticResponse()
    

async def get_task_info_by_id(task_id: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(HandleTaskRecord).filter_by(task_id=task_id)
            )
            if task_info:
                return TaskDetail.model_validate(task_info)
    return None
    

async def add_engineer(**kwargs):
    kwargs["create_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    kwargs["update_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_user = EngineerInfo(**kwargs)
            session.add(new_user)
    return GeneticResponse()


async def save_task_image(task_id: str, type: str, save_path: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(HandleTaskRecord).filter_by(task_id=task_id)
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