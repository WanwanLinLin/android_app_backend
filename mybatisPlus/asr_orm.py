import json
import redis
import requests
from sqlalchemy import desc, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (ASRFactories)
from .shelf_orm import binding_guard
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetASRList(BaseModel):
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


async def get_asr_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            # 存量数据 is_delete 可能为 NULL，NULL 与 False 均视为有效
            voices = await session.scalars(
                select(ASRFactories).where(
                    or_(ASRFactories.is_delete.is_(None), ASRFactories.is_delete.is_(False))))
            # total_len = len(voices.all())
            for i in voices.all():
                total_len += 1
                data = _GetASRList.model_validate(i).model_dump()
                results.append(data)
            return {"rows": results, "total": total_len}
        

async def add_one_asr(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            new_voice = ASRFactories(**kwargs)
            session.add(new_voice)
        return 1
    

async def get_one_asr(id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voice = await session.scalar(
                select(ASRFactories).filter_by(id=id))
            if voice:
                data = _GetASRList.model_validate(voice).model_dump()
                return data
            return None


async def update_one_asr(id: int, **kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            asr = await session.scalar(select(ASRFactories).filter_by(id=id))
            if not asr:
                return GeneticResponse(code=400, msg="data not exist")
            for k in ("type", "url", "desc", "apikey", "params"):
                if kwargs.get(k, None) is not None:
                    setattr(asr, k, kwargs.get(k))
            session.add(asr)
            return GeneticResponse()


async def delete_one_asr(id: int):
    """软删除语音识别模型。仍有租户绑定时拒绝，理由同 tts_orm.delete_one_voice。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            asr = await session.scalar(select(ASRFactories).filter_by(id=id))
            if not asr:
                return GeneticResponse(code=400, msg="data not exist")
            denied = await binding_guard("ASR", id, session)
            if denied:
                return denied
            asr.is_delete = True
            session.add(asr)
            return GeneticResponse()

