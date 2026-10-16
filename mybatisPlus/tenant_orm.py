from datetime import datetime
from typing import Union, List
from pydantic import BaseModel
from sqlalchemy import or_, select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import (ASRFactories, Tenant, SourceList, LLMFactories,
                                     TTSFactories, DigitalHumanChatTemplate, User)
from .tables.sqlcli import AsyncSessionLocal
from utils.common.enumTaskType import SourceTypeEnum
from utils.getLogs import LOG


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
    user_id: Union[int, None]
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
            user_id = kwargs.get("user_id")
            if user_id is not None:
                user = await session.scalar(select(User).filter_by(id=user_id))
                if not user:
                    return GeneticResponse(code=400, msg="user_id 对应的管理员不存在")
            new_tenant = Tenant(**kwargs)
            session.add(new_tenant)
            await session.flush()  # 先落库取回自增 id，否则返回 data.id 恒为 None
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
            if kwargs.get("user_id") is not None:
                user = await session.scalar(select(User).filter_by(id=kwargs.get("user_id")))
                if not user:
                    return GeneticResponse(code=400, msg="user_id 对应的管理员不存在")
            for k in ("user_id", "nickname", "job", "phone_number"):
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


# ===================== 租户资源绑定（Tenant 添加 tts/asr/llm 等资源）=====================

async def bind_source(tenant_id: int, type: str, reference_id: int):
    """把一条资源（SourceList 行）绑定到租户。

    同一 (type, reference_id, tenant_id) 已存在时直接返回成功（幂等），
    避免重复绑定产生脏数据。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(
                select(Tenant).filter_by(id=tenant_id, is_delete=False))
            if not tenant:
                return GeneticResponse(code=400, msg="租户不存在")
            exist = await session.scalar(
                select(SourceList).filter_by(
                    tenant_id=tenant_id, type=type, reference_id=reference_id))
            if exist:
                if exist.is_delete:
                    exist.is_delete = False
                    session.add(exist)
                return GeneticResponse(msg="已绑定")
            session.add(SourceList(tenant_id=tenant_id, type=type,
                                   reference_id=reference_id, is_delete=False))
            return GeneticResponse()


async def unbind_source(tenant_id: int, type: str, reference_id: int):
    """解绑（软删除 SourceList 行）。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            source = await session.scalar(
                select(SourceList).filter_by(
                    tenant_id=tenant_id, type=type, reference_id=reference_id))
            if not source:
                return GeneticResponse(code=400, msg="绑定关系不存在")
            source.is_delete = True
            session.add(source)
            return GeneticResponse()


async def list_bound_sources(tenant_id: int):
    """列出租户已绑定的资源（SourceList 行，含未绑定过滤）。"""
    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(SourceList).filter_by(tenant_id=tenant_id).where(
                or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False))))
        return [{"id": s.id, "type": s.type, "reference_id": s.reference_id,
                 "is_default": bool(s.is_default)} for s in rows]


async def set_source_default(tenant_id: int, type: str, reference_id: int):
    """把租户某类型下的指定绑定设为默认。

    同 (tenant_id, type) 下其余绑定 is_default 归零，仅目标为 1，
    保证每类型至多一个默认。对 TTS/ASR/LLM/CHATTEMPLATE 通用。
    沿用 save_default_source_config 的写法：SourceList.is_default 直接置 1。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant_id, type=type).where(
                    or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False))))
            rows = list(rows)
            target = next((r for r in rows if r.reference_id == reference_id), None)
            if not target:
                return GeneticResponse(code=400, msg="绑定关系不存在")
            for r in rows:
                r.is_default = (r.id == target.id)
                session.add(r)
            return GeneticResponse()


# ===================== 租户业务归属查询 =====================

async def list_tenants_by_username(username: str):
    """按后台管理员账号（User.username）取其名下的租户列表。

    归属关系走 Tenant.user_id 列（本项目不使用外键，引用完整性由应用层保证）：
    先按 username 查到 User.id，再取 Tenant.user_id 等于它的所有租户。安卓端用管理员账号
    登录后，据此拿到可操作的租户身份。

    软删过滤沿用列表口径：存量 is_delete 可能为 NULL，须 NULL 或 False 视为有效。
    """
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).filter_by(username=username).where(
                or_(User.is_delete.is_(None), User.is_delete.is_(False))))
        if not user:
            return None
        tenants = await session.scalars(
            select(Tenant).filter_by(user_id=user.id).where(
                or_(Tenant.is_delete.is_(None), Tenant.is_delete.is_(False)))
        )
        return [_TenantDetail.model_validate(t).model_dump() for t in tenants]


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


async def _tenant_default_source_ids(session, tenantname: str) -> dict:
    """取租户各类型下标记为默认的绑定，返回 {SourceTypeEnum.value: reference_id}。

    租户不存在或没有任何默认绑定时返回空 dict，由调用方决定兜底。
    同类型出现多行默认（历史脏数据）时取 id 最小的一行，保证结果稳定。
    is_delete 为 NULL 的存量行按有效处理，与本项目其余查询口径一致。
    """
    if not tenantname:
        return {}
    tenant = await session.scalar(select(Tenant).filter_by(tenantname=tenantname))
    if not tenant:
        return {}
    rows = await session.scalars(
        select(SourceList).filter_by(tenant_id=tenant.id, is_default=True).where(
            or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False)))
        .order_by(SourceList.id)
    )
    defaults = {}
    for r in rows:
        defaults.setdefault(r.type, r.reference_id)
    return defaults


async def get_source_config(**kwargs):
    """解析一次会话实际使用的 LLM / TTS / ASR / 对话模板。

    取值优先级：客户端 source_config 显式指定的 id > 租户在 SourceList 中的默认绑定
    > id=1 兜底。最后一级只为兼容从未配置过默认资源的历史终端，避免直接中断会话。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            defaults = await _tenant_default_source_ids(session, kwargs.get("uid"))

            def _resolve(id_key: str, source_type: str) -> int:
                given = kwargs.get(id_key)
                if given:
                    return given
                return defaults.get(source_type) or 1

            tts_id = _resolve("tts_id", SourceTypeEnum.TTS.value)
            asr_id = _resolve("asr_id", SourceTypeEnum.ASR.value)
            llm_id = _resolve("llm_id", SourceTypeEnum.LLM.value)

            async def _load(model, rid):
                """按 id 取资源行；绑定的资源已被删除时回落 id=1，避免 validate(None) 抛错。"""
                row = await session.scalar(select(model).filter_by(id=rid))
                if row is None and rid != 1:
                    LOG(f"租户 {kwargs.get('uid')} 的默认资源 {model.__name__}#{rid} 不存在，回落 id=1", "WARN")
                    row = await session.scalar(select(model).filter_by(id=1))
                return row

            tts_config = await _load(TTSFactories, tts_id)
            asr_config = await _load(ASRFactories, asr_id)
            llm_config = await _load(LLMFactories, llm_id)
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
