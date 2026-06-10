from datetime import datetime
import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from pydantic import BaseModel

from utils.common.schema import GeneticResponse
from .tables.work_order import Device2UserInfo, User
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal


class _EngineerDetail(BaseModel):
    id: Union[int, None]
    nickname: Union[str, None]
    job: Union[str, None]
    phone_number: Union[str, None]
    created_at: Union[datetime, str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("created_at")
    def get_created_time(cls, v, values):
        return datetime.strftime(v, '%Y-%m-%d %H:%M:%S')



class _DeviceDetail(BaseModel):
    id: Union[int, None]
    device_id: Union[str, None]
    location: Union[str, None]
    engineer_id: Union[int, None]
    create_time: Union[str, None]
    update_time: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


async def list_all_engineer():
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            _engineers = await session.scalars(
                select(User)
            )
            engineers = _engineers.all()
            if not engineers: return GeneticResponse(code=400, msg="工程师不存在。")
            data = [_EngineerDetail.model_validate(eng).model_dump() for eng in engineers]
            return GeneticResponse(data=data)


async def list_engineers_detail():
    async with WorkOrderAsyncSessionLocal() as db:
        # 1. 查询所有未删除工程师
        eng_stmt = select(User).filter_by(role="engineer")
        eng_result = await db.execute(eng_stmt)
        engineers = eng_result.scalars().all()

        if not engineers:
            return []

        # 2. 批量查所有设备（只查 1 次）
        eng_ids = [e.id for e in engineers]
        dev_stmt = select(Device2UserInfo).where(
            Device2UserInfo.engineer_id.in_(eng_ids),
            Device2UserInfo.is_delete == False
        )
        dev_result = await db.execute(dev_stmt)
        devices = dev_result.scalars().all()

        # 3. 按工程师分组设备
        device_map = {}
        for dev in devices:
            eid = dev.engineer_id
            if eid not in device_map:
                device_map[eid] = []
            device_map[eid].append(_DeviceDetail.model_validate(dev).model_dump())

        # 4. 合并返回：设备放进工程师字段里
        result = []
        for eng in engineers:
            eng_dict = _EngineerDetail.model_validate(eng).model_dump()
            eng_dict["device_list"] = device_map.get(eng.id, [])
            result.append(eng_dict)

        return result


async def get_engineer_by_id(_id: int):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            info = await session.scalar(
                select(User).filter_by(id=_id)
            )
            if info:
                return _EngineerDetail.model_validate(info)
    return 0


if __name__ == "__main__":
    import asyncio
    