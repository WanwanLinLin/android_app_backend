import json
import redis
import requests
from sqlalchemy import desc, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (DigitalHumanChatTemplate)
from .shelf_orm import binding_guard, active_only
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetChatTemplateList(BaseModel):
    id: int
    module_path: str
    desc: str
    status: Union[str, None] = None
    create_time: Union[datetime, str, None]
    update_time: Union[datetime, str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()

    @field_validator("status", mode="before")
    def norm_status(cls, v):
        # 迁移前的存量行 status 为 NULL，语义等同在售
        return v or "active"
        
    @field_validator("create_time")
    def get_create_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v

    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


async def get_chat_template_list(only_active: bool = False):
    """对话模板列表。only_active=True 时过滤掉已下架资源（非 admin 用），admin 看全量。"""
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            # 存量数据 is_delete 可能为 NULL，NULL 与 False 均视为有效
            stmt = select(DigitalHumanChatTemplate).where(
                or_(DigitalHumanChatTemplate.is_delete.is_(None),
                    DigitalHumanChatTemplate.is_delete.is_(False)))
            if only_active:
                stmt = stmt.where(active_only(DigitalHumanChatTemplate))
            templates = await session.scalars(stmt)
            for i in templates.all():
                total_len += 1
                data = _GetChatTemplateList.model_validate(i).model_dump()
                results.append(data)
            return {"rows": results, "total": total_len}
        

async def add_one_chat_template(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            template = DigitalHumanChatTemplate(**kwargs)
            session.add(template)
        return 1
    

async def get_one_chat_template(id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            template = await session.scalar(
                select(DigitalHumanChatTemplate).filter_by(id=id))
            if template:
                data = _GetChatTemplateList.model_validate(template).model_dump()
                return data
            return None


async def update_one_chat_template(id: int, **kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            template = await session.scalar(
                select(DigitalHumanChatTemplate).filter_by(id=id))
            if not template:
                return GeneticResponse(code=400, msg="data not exist")
            for k in ("module_path", "desc"):
                if kwargs.get(k, None) is not None:
                    setattr(template, k, kwargs.get(k))
            session.add(template)
            return GeneticResponse()


async def delete_one_chat_template(id: int):
    """软删除对话模板。仍有租户绑定时拒绝，理由同 tts_orm.delete_one_voice。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            template = await session.scalar(
                select(DigitalHumanChatTemplate).filter_by(id=id))
            if not template:
                return GeneticResponse(code=400, msg="data not exist")
            denied = await binding_guard("CHATTEMPLATE", id, session)
            if denied:
                return denied
            template.is_delete = True
            session.add(template)
            return GeneticResponse()

