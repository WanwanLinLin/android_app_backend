import json
import redis
import requests
from sqlalchemy import desc, select
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
        return datetime.strftime(v, "%Y-%m-%d %H:%M:%S")
    
    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return datetime.strftime(v, "%Y-%m-%d %H:%M:%S")


async def get_chat_template_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            templates = await session.scalars(
                select(DigitalHumanChatTemplate))
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

