import json
import redis
import requests
from sqlalchemy import desc, func, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (TTSFactories, TTScache)
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
    additional_param: Union[dict, None]
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


async def get_voice_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voices = await session.scalars(
                select(TTSFactories))
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
