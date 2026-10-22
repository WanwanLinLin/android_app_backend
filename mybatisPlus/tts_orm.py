import json
import redis
import requests
from sqlalchemy import desc, func, or_, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (TTSFactories, TTScache)
from .shelf_orm import binding_guard, active_only
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetTTSList(BaseModel):
    id: int
    type: Union[str, None]
    url: Union[str, None]
    desc: Union[str, None]
    tag: Union[str, None]
    voice: Union[str, None]
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
        # 列默认值为字符串 "{}"，存量数据可能存的是 JSON 文本而非 dict
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v

    @field_validator("create_time", "update_time", mode="before")
    def _none_time(cls, v):
        return v if v else None

    @field_validator("create_time")
    def get_create_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v

    @field_validator("update_time")
    def get_update_time(cls, v, values):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


async def get_voice_list(only_active: bool = False):
    """TTS 列表。

    only_active=True 时过滤掉已下架资源——非 admin 角色用这个口径，
    下架的资源对他们既不可见也不可绑定；admin 看全量以便重新上架。
    """
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            # 存量数据 is_delete 可能为 NULL，NULL 与 False 均视为有效
            stmt = select(TTSFactories).where(
                or_(TTSFactories.is_delete.is_(None), TTSFactories.is_delete.is_(False)))
            if only_active:
                stmt = stmt.where(active_only(TTSFactories))
            voices = await session.scalars(stmt)
            # total_len = len(voices.all())
            for i in voices.all():
                total_len += 1
                data = _GetTTSList.model_validate(i).model_dump()
                results.append(data)
            return {"rows": results, "total": total_len}
        

async def add_one_voice(**kwargs):
    # now_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    # kwargs["create_time"] = now_time
    # kwargs["update_time"] = now_time
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            new_voice = TTSFactories(**kwargs)
            session.add(new_voice)
        return 1
    

async def get_one_voice(id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voice = await session.scalar(
                select(TTSFactories).filter_by(id=id))
            if voice:
                data = _GetTTSList.model_validate(voice).model_dump()
                return data
            return None


async def update_one_voice(id: int, **kwargs):
    """更新音色。2026-10-22 起旧资源池仅开放 params 编辑（其余字段随旧池下线锁定）。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            voice = await session.scalar(select(TTSFactories).filter_by(id=id))
            if not voice:
                return GeneticResponse(code=400, msg="data not exist")
            if kwargs.get("params", None) is not None:
                voice.params = kwargs.get("params")
            session.add(voice)
            return GeneticResponse()


async def delete_one_voice(id: int):
    """软删除音色。仍有租户绑定时拒绝——删除会让 SourceList 引用悬空，
    租户配置直接失效；只是想停用请改用下架（off_shelf，存量绑定不受影响）。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            voice = await session.scalar(select(TTSFactories).filter_by(id=id))
            if not voice:
                return GeneticResponse(code=400, msg="data not exist")
            denied = await binding_guard("TTS", id, session)
            if denied:
                return denied
            voice.is_delete = True
            session.add(voice)
            return GeneticResponse()


async def handle_audio_file(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            if kwargs.get("op"):
                audio_file = await session.scalar(
                    select(TTScache).filter(TTScache.tag==kwargs.get("tag"), TTScache.sec_text==kwargs.get("sec_text"),
                                            TTScache.voice==kwargs.get("voice"), TTScache.format==kwargs.get("format"), TTScache.sr==kwargs.get("sr"),
                                            func.abs(TTScache.speed - kwargs.get("speed")) < 0.0001))
                if audio_file:
                    return audio_file.save_path
                return 0
            else:
                del kwargs["op"]
                new_file = TTScache(**kwargs)
                session.add(new_file)
                return 1
    
    return
