import json
import redis
import requests
from sqlalchemy import desc, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta
from .tables.industrial_park import (FigureFactories)
from .tables.sqlcli import Base, async_engine, AsyncSessionLocal
from utils.randomString import create_numbering
from utils.common.schema import GeneticResponse
from setting import *


class _GetFigureList(BaseModel):
    id: int
    type: Union[str, None]
    name: Union[str, None]
    filename: Union[str, None]
    author: Union[str, None]
    version: Union[str, None]
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


async def get_figure_list():
    results = []
    total_len = 0
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voices = await session.scalars(
                select(FigureFactories))
            # total_len = len(voices.all())
            for i in voices.all():
                total_len += 1
                data = _GetFigureList.model_validate(i).model_dump()
                results.append(data)
            return {"rows": results, "total": total_len}
        

async def add_one_figure(**kwargs):
    # now_time = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    # kwargs["create_time"] = now_time
    # kwargs["update_time"] = now_time
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            new_voice = FigureFactories(**kwargs)
            session.add(new_voice)
        return 1
    

async def get_one_figure(id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():  # 开启事务
            voice = await session.scalar(
                select(FigureFactories).filter_by(id=id))
            if voice:
                data = _GetFigureList.model_validate(voice).model_dump()
                return data
            return None

