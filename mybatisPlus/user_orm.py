from datetime import datetime
from typing import Union
from pydantic import BaseModel
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import ASRFactories, Device2UserInfo, User, SourceList, LLMFactories, TTSFactories
from .tables.sqlcli import AsyncSessionLocal
from utils.common.enumTaskType import SourceTypeEnum


class UserModel(BaseModel):
    device_id: str
    username: str
    phone_number: str


class _GetLLMList(BaseModel):
    id: int
    type: Union[str, None]
    desc: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        

class _GetASRList(BaseModel):
    id: int
    type: Union[str, None]
    desc: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


class _GetTTSList(BaseModel):
    id: int
    type: Union[str, None]
    desc: Union[str, None]
    tag: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        

class _GetLLMList2(BaseModel):
    id: int
    url: Union[str, None]
    type: Union[str, None]
    desc: Union[str, None]
    apikey: Union[str, None]
    params: Union[dict, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()
        

class _GetASRList2(BaseModel):
    id: int
    url: Union[str, None]
    type: Union[str, None]
    desc: Union[str, None]
    apikey: Union[str, None]
    params: Union[dict, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


class _GetTTSList2(BaseModel):
    id: int
    url: Union[str, None]
    type: Union[str, None]
    desc: Union[str, None]
    tag: Union[str, None]
    voice: Union[str, None]
    apikey: Union[str, None]
    
    class Config:
        from_attributes = True
        protected_namespaces = ()


async def get_password(username: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await session.scalar(select(User).filter_by(username=username))
            if not user: return None
            return user.hashed_password
        

async def get_source_list(username: str):
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
            llm_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.LLM.value]
            tts_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.TTS.value]
            asr_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.ASR.value]

            # 3. 批量加载 LLMFactories（最多一次）
            llm_map = {}
            if llm_ids:
                llms = await session.scalars(
                    select(LLMFactories).where(LLMFactories.id.in_(llm_ids))
                )
                llm_map = {llm.id: llm for llm in llms}

            # 4. 批量加载 TTSFactories（最多一次）
            tts_map = {}
            if tts_ids:
                ttss = await session.scalars(
                    select(TTSFactories).where(TTSFactories.id.in_(tts_ids))
                )
                tts_map = {tts.id: tts for tts in ttss}
                
            # 4. 批量加载 ASRFactories（最多一次）
            asr_map = {}
            if asr_ids:
                asrs = await session.scalars(
                    select(ASRFactories).where(ASRFactories.id.in_(asr_ids))
                )
                asr_map = {asr.id: asr for asr in asrs}

            # 组装结果
            llm_list = []
            tts_list = []
            asr_list = []
            for s in sources:
                if s.type == SourceTypeEnum.LLM.value:
                    llm_info = llm_map.get(s.reference_id)
                    if llm_info:
                        llm_list.append(_GetLLMList.model_validate(llm_info).model_dump())
                elif s.type == SourceTypeEnum.TTS.value:
                    tts_info = tts_map.get(s.reference_id)
                    if tts_info:
                        tts_list.append(_GetTTSList.model_validate(tts_info).model_dump())
                elif s.type == SourceTypeEnum.ASR.value:
                    asr_info = asr_map.get(s.reference_id)
                    if asr_info:
                        asr_list.append(_GetASRList.model_validate(asr_info).model_dump())

            return {"llm": llm_list, "tts": tts_list, "asr": asr_list}


async def get_source_config(**kwargs):
    tts_id = kwargs.get("tts_id", 1)
    asr_id = kwargs.get("asr_id", 1)
    llm_id = kwargs.get("llm_id", 1)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tts_config = await session.scalar(select(TTSFactories).filter_by(id=tts_id))
            asr_config = await session.scalar(select(ASRFactories).filter_by(id=asr_id))
            llm_config = await session.scalar(select(LLMFactories).filter_by(id=llm_id))
            
            return {
                "tts_config": _GetTTSList2.model_validate(tts_config).model_dump(),
                "asr_config": _GetASRList2.model_validate(asr_config).model_dump(),
                "llm_config": _GetLLMList2.model_validate(llm_config).model_dump()
            }


if __name__ == "__main__":
    import asyncio
    