import json
import redis
import requests
from sqlalchemy import desc, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (LLMFactories, AgentSessionManagement, Tenant)
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetLLMList(BaseModel):
    id: int
    type: Union[str, None]
    url: Union[str, None]
    desc: Union[str, None]
    apikey: Union[str, None]
    params: Union[dict, None]
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


async def get_agent_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voices = await session.scalars(
                select(LLMFactories))
            # total_len = len(voices.all())
            for i in voices.all():
                total_len += 1
                data = _GetLLMList.model_validate(i).model_dump()
                results.append(data)
            return {"rows": results, "total": total_len}
        

async def add_one_agent(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            new_voice = LLMFactories(**kwargs)
            session.add(new_voice)
        return 1
    

async def get_one_agent(id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voice = await session.scalar(
                select(LLMFactories).filter_by(id=id))
            if voice:
                data = _GetLLMList.model_validate(voice).model_dump()
                return data
            return None


async def manage_agent_session(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            _type = kwargs.get("type")
            del kwargs["type"]
            if _type == "create":
                tenant = await session.scalar(select(Tenant).filter_by(tenantname=kwargs["tenant_id"]))
                kwargs["tenant_id"] = tenant.id
                new_record = AgentSessionManagement(**kwargs)
                session.add(new_record)
                return True
            elif _type == "update":
                info = await session.scalar(select(AgentSessionManagement).filter_by(session_id=kwargs["session_id"]))
                info.dialogue_history = kwargs["dialogue_history"]
                session.add(info)
                return True
            else:
                return False
                