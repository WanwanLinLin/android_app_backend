import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import Device2UserInfo, HandleTaskRecord, EngineerInfo
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal
from datetime import datetime


class DeviceDetail(BaseModel):
    id: Union[int, None]
    device_id: Union[str, None]
    location: Union[str, None]
    engineer_id: Union[int, None]
    create_time: Union[str, None]
    update_time: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


async def update_location(device_id: str, location: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            info = await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
            )
            if info:
                info.device_id = device_id
                info.location = location
                info.update_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
                session.add(info)
                return GeneticResponse()
            return GeneticResponse(code=400, msg="设备不存在")
        

async def get_device_detail_by_engineer_id(engineer_id: int):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            info = await session.scalar(
                select(Device2UserInfo).filter_by(engineer_id=engineer_id)
            )
            if info:
                return DeviceDetail.model_validate(info)
    return None


async def get_device_detail_by_device_id(device_id: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            info = await session.scalar(
                select(Device2UserInfo).filter_by(device_id=device_id)
            )
            if info:
                return DeviceDetail.model_validate(info)
    return None


# async def add_device(**kwargs):
#     kwargs["create_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
#     kwargs["update_time"] = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             new_user = Device2UserInfo(**kwargs)
#             session.add(new_user)
#     return GeneticResponse()