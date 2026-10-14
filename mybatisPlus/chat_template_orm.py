import json
import redis
import requests
from sqlalchemy import desc, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (DigitalHumanChatTemplate)
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetChatTemplateList(BaseModel):
    id: int
    module_path: str
    desc: str
    create_time: Union[datetime, str, None]
    update_time: Union[datetime, str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        
    @field_validator("create_time")
    def get_create_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v

    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


async def get_chat_template_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            # 存量数据 is_delete 可能为 NULL，NULL 与 False 均视为有效
            templates = await session.scalars(
                select(DigitalHumanChatTemplate).where(
                    or_(DigitalHumanChatTemplate.is_delete.is_(None),
                        DigitalHumanChatTemplate.is_delete.is_(False))))
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
    """软删除对话模板。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            template = await session.scalar(
                select(DigitalHumanChatTemplate).filter_by(id=id))
            if not template:
                return GeneticResponse(code=400, msg="data not exist")
            template.is_delete = True
            session.add(template)
            return GeneticResponse()

