import json
import redis
import requests
from sqlalchemy import desc, select
from pydantic import BaseModel, field_validator
from typing import Union, List, Dict

from datetime import datetime
from datetime import datetime, timedelta

from utils.common.enumTaskType import SourceTypeEnum
from .tables.industrial_park import (FigureFactories, User, SourceList)
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
    desc: Union[str, None]
    savename: Union[str, None]
    version: Union[str, None]
    resolution: Union[List, None]
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



async def get_user_figure_list(username: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. 查询用户（仅一次）
            user = await session.scalar(select(User).filter_by(username=username))
            if not user:
                return None

            # 2. 查询该用户的所有 source（一次）
            sources = await session.scalars(
                select(SourceList).filter_by(user_id=user.id)
            )
            sources = list(sources)  # 转为列表便于多次迭代

            # 按类型收集 reference_id
            figure_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.FIGURE.value]
            background_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.BACKGROUND.value]

            # 3. 批量加载 LLMFactories（最多一次）
            figure_map = {}
            if figure_ids:
                llms = await session.scalars(
                    select(FigureFactories).where(FigureFactories.id.in_(figure_ids))
                )
                figure_map = {llm.id: llm for llm in llms}

            # 4. 批量加载 TTSFactories（最多一次）
            background_map = {}
            if background_ids:
                ttss = await session.scalars(
                    select(FigureFactories).where(FigureFactories.id.in_(background_ids))
                )
                background_map = {tts.id: tts for tts in ttss}
                

            # 组装结果
            figure_list = []
            for s in sources:
                if s.type == SourceTypeEnum.FIGURE.value:
                    llm_info = figure_map.get(s.reference_id)
                    if llm_info:
                        figure_list.append(_GetFigureList.model_validate(llm_info).model_dump())
                elif s.type == SourceTypeEnum.BACKGROUND.value:
                    tts_info = background_map.get(s.reference_id)
                    if tts_info:
                        figure_list.append(_GetFigureList.model_validate(tts_info).model_dump())

            return figure_list