from datetime import datetime
from typing import Union, List
from pydantic import BaseModel
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import (ASRFactories, Tenant, SourceList, LLMFactories,
                                     TTSFactories, DigitalHumanChatTemplate)
from .tables.sqlcli import AsyncSessionLocal
from utils.common.enumTaskType import SourceTypeEnum


class TenantModel(BaseModel):
    tenantname: str
    nickname: Union[str, None] = None
    job: Union[str, None] = None
    phone_number: Union[str, None] = None


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
    additional_param: Union[dict, None]

    class Config:
        from_attributes = True
        protected_namespaces = ()


class _GetChatTemplateList2(BaseModel):
    id: int
    module_path: Union[str, None]
    desc: Union[str, None]

    class Config:
        from_attributes = True
        protected_namespaces = ()


class _TenantDetail(BaseModel):
    id: int
    tenantname: Union[str, None]
    nickname: Union[str, None]
    job: Union[str, None]
    phone_number: Union[str, None]

    class Config:
        from_attributes = True
        protected_namespaces = ()


# ===================== 租户生命周期管理（User 管理员操作）=====================

async def create_tenant(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            exist = await session.scalar(
                select(Tenant).filter_by(tenantname=kwargs.get("tenantname"))
            )
            if exist:
                return GeneticResponse(code=400, msg="租户已存在")
            new_tenant = Tenant(**kwargs)
            session.add(new_tenant)
            return GeneticResponse(data={"id": new_tenant.id})


async def list_tenants():
    async with AsyncSessionLocal() as session:
        tenants = await session.scalars(select(Tenant).filter_by(is_delete=False))
        return [_TenantDetail.model_validate(t).model_dump() for t in tenants]


async def get_tenant(tenant_id: int):
    async with AsyncSessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant).filter_by(id=tenant_id, is_delete=False)
        )
        if not tenant:
            return None
        return _TenantDetail.model_validate(tenant).model_dump()


async def update_tenant(tenant_id: int, **kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(
                select(Tenant).filter_by(id=tenant_id, is_delete=False)
            )
            if not tenant:
                return GeneticResponse(code=400, msg="租户不存在")
            for k in ("nickname", "job", "phone_number"):
                if kwargs.get(k, None) is not None:
                    setattr(tenant, k, kwargs.get(k))
            session.add(tenant)
            return GeneticResponse()


async def delete_tenant(tenant_id: int):
    """软删除租户。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).filter_by(id=tenant_id))
            if not tenant:
                return GeneticResponse(code=400, msg="租户不存在")
            tenant.is_delete = True
            session.add(tenant)
            return GeneticResponse()


# ===================== 租户业务归属查询 =====================

async def get_source_list(tenantname: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).filter_by(tenantname=tenantname))
            if not tenant:
                return None

            sources = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant.id)
            )
            sources = list(sources)

            llm_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.LLM.value]
            tts_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.TTS.value]
            asr_ids = [s.reference_id for s in sources if s.type == SourceTypeEnum.ASR.value]

            llm_map = {}
            if llm_ids:
                llms = await session.scalars(select(LLMFactories).where(LLMFactories.id.in_(llm_ids)))
                llm_map = {llm.id: llm for llm in llms}

            tts_map = {}
            if tts_ids:
                ttss = await session.scalars(select(TTSFactories).where(TTSFactories.id.in_(tts_ids)))
                tts_map = {tts.id: tts for tts in ttss}

            asr_map = {}
            if asr_ids:
                asrs = await session.scalars(select(ASRFactories).where(ASRFactories.id.in_(asr_ids)))
                asr_map = {asr.id: asr for asr in asrs}

            llm_list, tts_list, asr_list = [], [], []
            for s in sources:
                if s.type == SourceTypeEnum.LLM.value:
                    info = llm_map.get(s.reference_id)
                    if info:
                        llm_list.append(_GetLLMList.model_validate(info).model_dump())
                elif s.type == SourceTypeEnum.TTS.value:
                    info = tts_map.get(s.reference_id)
                    if info:
                        tts_list.append(_GetTTSList.model_validate(info).model_dump())
                elif s.type == SourceTypeEnum.ASR.value:
                    info = asr_map.get(s.reference_id)
                    if info:
                        asr_list.append(_GetASRList.model_validate(info).model_dump())

            return {"llm": llm_list, "tts": tts_list, "asr": asr_list}


async def get_source_config(**kwargs):
    tts_id = kwargs.get("tts_id") if kwargs.get("tts_id", None) else 1
    asr_id = kwargs.get("asr_id") if kwargs.get("asr_id", None) else 1
    llm_id = kwargs.get("llm_id") if kwargs.get("llm_id", None) else 1
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tts_config = await session.scalar(select(TTSFactories).filter_by(id=tts_id))
            asr_config = await session.scalar(select(ASRFactories).filter_by(id=asr_id))
            llm_config = await session.scalar(select(LLMFactories).filter_by(id=llm_id))
            stmt = (
                select(DigitalHumanChatTemplate)
                .join(SourceList, SourceList.reference_id == DigitalHumanChatTemplate.id)
                .join(Tenant, Tenant.id == SourceList.tenant_id)
                .where(
                    Tenant.tenantname == kwargs.get("uid"),
                    SourceList.type == SourceTypeEnum.CHATTEMPLATE.value,
                    SourceList.is_default.is_(True),
                )
                .limit(1)
            )
            chat_template_config = await session.scalar(stmt)
            if not chat_template_config:
                # 该租户未设置默认对话模板时，回退到库中任一可用模板，
                # 避免下游 importlib 拿到空 module_path 而中断会话。
                chat_template_config = await session.scalar(
                    select(DigitalHumanChatTemplate).filter_by(is_delete=False).limit(1)
                )
            return {
                "tts_config": _GetTTSList2.model_validate(tts_config).model_dump(),
                "asr_config": _GetASRList2.model_validate(asr_config).model_dump(),
                "llm_config": _GetLLMList2.model_validate(llm_config).model_dump(),
                "chat_template_config": (
                    _GetChatTemplateList2.model_validate(chat_template_config).model_dump()
                    if chat_template_config else {"id": None, "module_path": None, "desc": None}
                ),
            }


async def get_default_source_config(tenantname: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).filter_by(tenantname=tenantname))
            if not tenant:
                return None
            sources = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant.id, is_default=True)
            )
            llm_config = tts_config = asr_config = None
            for s in sources:
                if s.type == SourceTypeEnum.LLM.value:
                    llm_config = await session.scalar(select(LLMFactories).filter_by(id=s.reference_id))
                elif s.type == SourceTypeEnum.TTS.value:
                    tts_config = await session.scalar(select(TTSFactories).filter_by(id=s.reference_id))
                elif s.type == SourceTypeEnum.ASR.value:
                    asr_config = await session.scalar(select(ASRFactories).filter_by(id=s.reference_id))

            return {
                "llm_config": _GetLLMList.model_validate(llm_config).model_dump() if llm_config else None,
                "tts_config": _GetTTSList.model_validate(tts_config).model_dump() if tts_config else None,
                "asr_config": _GetASRList.model_validate(asr_config).model_dump() if asr_config else None,
            }


async def save_default_source_config(**kwargs):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(
                select(Tenant).filter_by(tenantname=kwargs.get("tenantname"))
            )
            if not tenant:
                return 0
            sources = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant.id, is_default=True)
            )
            for s in sources:
                if s.type in (SourceTypeEnum.LLM.value, SourceTypeEnum.TTS.value, SourceTypeEnum.ASR.value):
                    s.is_default = False
                    session.add(s)
            for _type, id_key in ((SourceTypeEnum.LLM.value, "llm_id"),
                                  (SourceTypeEnum.TTS.value, "tts_id"),
                                  (SourceTypeEnum.ASR.value, "asr_id")):
                source = await session.scalar(
                    select(SourceList).filter_by(
                        tenant_id=tenant.id, type=_type, reference_id=kwargs.get(id_key))
                )
                if source:
                    source.is_default = 1
                    session.add(source)
            return 1
