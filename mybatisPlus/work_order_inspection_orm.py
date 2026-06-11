import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.work_order import Task, InspectionTask, NfcFloor, Device2UserInfo, User
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal
from datetime import datetime


class _InspectionDetail(BaseModel):
    id: Union[int, None]
    task_id: Union[str, None]
    title: Union[str, None]
    start_time: Union[str, None]
    status: Union[int, None]
    floor_ids: Union[List, str, None]
    process_msg: Union[List, str, None]
    checked_floor_ids: Union[List, str, None]
    assignee_ids: Union[List, str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("floor_ids")
    def get_floor_ids(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)
    
    @field_validator("process_msg")
    def get_process_msg(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)
    
    @field_validator("checked_floor_ids")
    def get_checked_floor_ids(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)
    
    @field_validator("assignee_ids")
    def get_assignee_ids(cls, v, values):
        if not v: return []
        return json.loads(v, strict=False)


class _NfcFloorDetail(BaseModel):
    id: Union[int, None]
    nfc_code: Union[str, None]
    floor_name: Union[str, None]
    created_at: Union[datetime, str, None]
    updated_at: Union[datetime, str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("created_at")
    def get_created_at(cls, v, values):
        return datetime.strftime(v, "%Y-%m-%d %H:%M:%S")
    
    @field_validator("updated_at")
    def get_updated_at(cls, v, values):
        return datetime.strftime(v, "%Y-%m-%d %H:%M:%S")


async def wo_get_inspection_info_by_task_id(task_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                floor_name = []
                checked_floor_name = []
                device_ids = []
                _task_detail = _InspectionDetail.model_validate(task_info).model_dump()
                for i in _task_detail["floor_ids"]:
                    nf_info = await session.scalar(select(NfcFloor).filter_by(id=i))
                    floor_name.append(nf_info.floor_name)
                for j in _task_detail["checked_floor_ids"]:
                    nf_info = await session.scalar(select(NfcFloor).filter_by(id=j))
                    checked_floor_name.append(nf_info.floor_name)
                for z in _task_detail["assignee_ids"]:
                    device_info = await session.scalar(select(Device2UserInfo).filter_by(engineer_id=z))
                    device_ids.append(device_info.device_id)
                _task_detail["floor_name"] = floor_name
                _task_detail["checked_floor_name"] = checked_floor_name
                _task_detail["device_ids"] = device_ids
                return _task_detail
    return None


async def wo_get_nfc_info():
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            info = await session.scalars(
                select(NfcFloor)
            )
            if info:
                return [_NfcFloorDetail.model_validate(i).model_dump() for i in info]
    return None


async def wo_get_all_unstart_tasks():
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalars(
                select(InspectionTask).filter_by(status=0)
            )
            if task_info:
                res = []
                for t in task_info:
                    floor_name = []
                    checked_floor_name = []
                    _task_detail = _InspectionDetail.model_validate(t).model_dump()
                    for i in _task_detail["floor_ids"]:
                        nf_info = await session.scalar(select(NfcFloor).filter_by(id=i))
                        floor_name.append(nf_info.floor_name)
                    for j in _task_detail["checked_floor_ids"]:
                        nf_info = await session.scalar(select(NfcFloor).filter_by(id=j))
                        checked_floor_name.append(nf_info.floor_name)
                    _task_detail["floor_name"] = floor_name
                    _task_detail["checked_floor_name"] = checked_floor_name
                    res.append(_task_detail)
                return res
    return None


async def wo_start_inspection_task(task_id: str, device_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                user_info = await session.scalar(
                select(User).filter_by(id=(await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
                )).engineer_id)
                )
                process_msg = f'{datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")} {user_info.nickname} 确认巡检任务。'
                task_info.status = 1
                process_msg_list = json.loads(task_info.process_msg, strict=False)
                process_msg_list.append(process_msg)
                task_info.process_msg = json.dumps(process_msg_list, ensure_ascii=False)
                session.add(task_info)
                return 1
    return None


async def wo_check_in_inspection_task(task_id: str, nfc_code: str, device_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                user_info = await session.scalar(
                select(User).filter_by(id=(await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
                )).engineer_id)
                )
                nfc_floor_info = await session.scalar(select(NfcFloor).filter_by(nfc_code=nfc_code))
                process_msg = f'{datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")} {user_info.nickname} 已经巡检完{nfc_floor_info.floor_name}并打卡。'
                process_msg_list = json.loads(task_info.process_msg, strict=False)
                process_msg_list.append(process_msg)
                task_info.process_msg = json.dumps(process_msg_list, ensure_ascii=False)
                
                checked_floor_ids_list = json.loads(task_info.checked_floor_ids, strict=False)
                checked_floor_ids_list.append(nfc_floor_info.id)
                task_info.checked_floor_ids = json.dumps(checked_floor_ids_list, ensure_ascii=False)
                
                session.add(task_info)
                return 1
    return None


async def wo_order_inspection_floors(task_id: str, floor_ids: List[int]):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                task_info.floor_ids = json.dumps(floor_ids, ensure_ascii=False)
                session.add(task_info)
                return 1
    return None


async def wo_update_inspection_status(task_id: str, status: int):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                task_info.status = status
                session.add(task_info)
                return 1
    return None


async def wo_update_inspection_check_floors_ids(task_id: str, checked_floor_ids: List[int]):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                task_info.checked_floor_ids = json.dumps(checked_floor_ids, ensure_ascii=False)
                session.add(task_info)
                return 1
    return None


async def wo_update_inspection_process_msg(task_id: str, process_msg: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            task_info = await session.scalar(
                select(InspectionTask).filter_by(task_id=task_id)
            )
            if task_info:
                process_msg = f'{datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")} 智能体介入: {process_msg}'
                process_msg_list = json.loads(task_info.process_msg, strict=False)
                process_msg_list.append(process_msg)
                task_info.process_msg = json.dumps(process_msg_list, ensure_ascii=False)
                
                session.add(task_info)
                return 1
    return None