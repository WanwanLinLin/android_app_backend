import json
import redis
import requests
from sqlalchemy import desc, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (LLMFactories, AgentSessionManagement, Tenant)
from .shelf_orm import binding_guard, active_only
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

    @field_validator("params", mode="before")
    def parse_params(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v

    @field_validator("create_time")
    def get_create_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v

    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


async def get_agent_list(only_active: bool = False):
    """LLM 列表。only_active=True 时过滤掉已下架资源（非 admin 用），admin 看全量。"""
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            # 存量数据 is_delete 可能为 NULL，NULL 与 False 均视为有效
            stmt = select(LLMFactories).where(
                or_(LLMFactories.is_delete.is_(None), LLMFactories.is_delete.is_(False)))
            if only_active:
                stmt = stmt.where(active_only(LLMFactories))
            voices = await session.scalars(stmt)
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


async def update_one_agent(id: int, **kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            llm = await session.scalar(select(LLMFactories).filter_by(id=id))
            if not llm:
                return GeneticResponse(code=400, msg="data not exist")
            for k in ("type", "url", "desc", "apikey", "params"):
                if kwargs.get(k, None) is not None:
                    setattr(llm, k, kwargs.get(k))
            session.add(llm)
            return GeneticResponse()


async def delete_one_agent(id: int):
    """软删除大模型。仍有租户绑定时拒绝，理由同 tts_orm.delete_one_voice。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            llm = await session.scalar(select(LLMFactories).filter_by(id=id))
            if not llm:
                return GeneticResponse(code=400, msg="data not exist")
            denied = await binding_guard("LLM", id, session)
            if denied:
                return denied
            llm.is_delete = True
            session.add(llm)
            return GeneticResponse()


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
                