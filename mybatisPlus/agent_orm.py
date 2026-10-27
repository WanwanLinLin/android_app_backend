import json
import redis
import requests
from sqlalchemy import desc, func, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (ASRFactories, LLMFactories, TTSFactories, AgentSessionManagement, Tenant)
from .shelf_orm import binding_guard, active_only
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from utils.secret_mask import restore_masked
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
    """更新大模型。2026-10-22 起旧资源池仅开放 params 编辑（其余字段随旧池下线锁定）。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            llm = await session.scalar(select(LLMFactories).filter_by(id=id))
            if not llm:
                return GeneticResponse(code=400, msg="data not exist")
            if kwargs.get("params", None) is not None:
                # params 内 apikey/Authorization 展示层已掩码为 "***"，未改动时回填原值
                llm.params = restore_masked(kwargs.get("params"), llm.params)
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


class _GetSessionList(BaseModel):
    id: int
    session_id: Union[str, None]
    tenant_id: Union[int, None]
    agent_id: Union[int, None]
    asr_id: Union[int, None]
    tts_id: Union[int, None]
    create_time: Union[datetime, str, None]
    update_time: Union[datetime, str, None]
    tenantname: Union[str, None] = None
    llm_desc: Union[str, None] = None
    asr_desc: Union[str, None] = None
    tts_desc: Union[str, None] = None
    rounds: Union[int, None] = None

    class Config:
        from_attributes = True
        protected_namespaces = ()

    @field_validator("create_time")
    def get_create_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v

    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


class _GetSessionDetail(_GetSessionList):
    dialogue_history: Union[list, str, None] = None

    @field_validator("dialogue_history", mode="before")
    def parse_history(cls, v):
        # JSON 列存量数据可能是字符串形态，统一解析为 list 供前端渲染
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v


async def get_session_list(tenant_ids: List[int] = None, start: str = None, end: str = None,
                           page: int = 1, size: int = 20):
    """会话记录分页列表（只读审计）。

    tenant_ids：权限收窄——非 admin 传自己名下租户 id 列表；None 表示不限。
    start/end：create_time 闭区间，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS。
    列表不带 dialogue_history 大字段，详情走 get_one_session。
    join 出租户名与 LLM/ASR/TTS 描述（outer join，资源删除后历史会话仍可展示）。
    rounds 为 dialogue_history 的 JSON 数组长度（消息条数），NULL 计 0。
    """
    async with AsyncSessionLocal() as session:
        cond = [or_(AgentSessionManagement.is_delete.is_(None),
                    AgentSessionManagement.is_delete.is_(False))]
        if tenant_ids is not None:
            if not tenant_ids:
                return {"rows": [], "total": 0}
            cond.append(AgentSessionManagement.tenant_id.in_(tenant_ids))
        if start:
            cond.append(AgentSessionManagement.create_time >= start)
        if end:
            cond.append(AgentSessionManagement.create_time <= (end if len(end) > 10 else end + " 23:59:59"))
        total = await session.scalar(
            select(func.count()).select_from(AgentSessionManagement).where(*cond))
        stmt = (select(AgentSessionManagement, Tenant.tenantname,
                       LLMFactories.desc.label("llm_desc"),
                       ASRFactories.desc.label("asr_desc"),
                       TTSFactories.desc.label("tts_desc"),
                       func.coalesce(func.json_length(AgentSessionManagement.dialogue_history), 0).label("rounds"))
                .outerjoin(Tenant, Tenant.id == AgentSessionManagement.tenant_id)
                .outerjoin(LLMFactories, LLMFactories.id == AgentSessionManagement.agent_id)
                .outerjoin(ASRFactories, ASRFactories.id == AgentSessionManagement.asr_id)
                .outerjoin(TTSFactories, TTSFactories.id == AgentSessionManagement.tts_id)
                .where(*cond)
                .order_by(desc(AgentSessionManagement.create_time))
                .offset(max(page - 1, 0) * size).limit(size))
        rows = []
        for sess, tenantname, llm_desc, asr_desc, tts_desc, rounds in (await session.execute(stmt)).all():
            data = _GetSessionList.model_validate(sess).model_dump()
            data.update(tenantname=tenantname, llm_desc=llm_desc, asr_desc=asr_desc,
                        tts_desc=tts_desc, rounds=rounds)
            rows.append(data)
        return {"rows": rows, "total": total or 0}


async def get_one_session(id: int):
    """单条会话详情（含 dialogue_history 全文，供聊天气泡渲染）。"""
    async with AsyncSessionLocal() as session:
        stmt = (select(AgentSessionManagement, Tenant.tenantname,
                       LLMFactories.desc.label("llm_desc"),
                       ASRFactories.desc.label("asr_desc"),
                       TTSFactories.desc.label("tts_desc"),
                       func.coalesce(func.json_length(AgentSessionManagement.dialogue_history), 0).label("rounds"))
                .outerjoin(Tenant, Tenant.id == AgentSessionManagement.tenant_id)
                .outerjoin(LLMFactories, LLMFactories.id == AgentSessionManagement.agent_id)
                .outerjoin(ASRFactories, ASRFactories.id == AgentSessionManagement.asr_id)
                .outerjoin(TTSFactories, TTSFactories.id == AgentSessionManagement.tts_id)
                .where(AgentSessionManagement.id == id))
        row = (await session.execute(stmt)).first()
        if not row:
            return None
        sess, tenantname, llm_desc, asr_desc, tts_desc, rounds = row
        data = _GetSessionDetail.model_validate(sess).model_dump()
        data.update(tenantname=tenantname, llm_desc=llm_desc, asr_desc=asr_desc,
                    tts_desc=tts_desc, rounds=rounds)
        return data


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
                