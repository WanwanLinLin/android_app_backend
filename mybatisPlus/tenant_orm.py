from datetime import datetime
from typing import Union, List
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from utils.common.schema import GeneticResponse
from .tables.industrial_park import (ASRFactories, Tenant, SourceList, LLMFactories,
                                     TTSFactories, DigitalHumanChatTemplate, User,
                                     BasePlugin, CustomPlugin,
                                     STATUS_ACTIVE, STATUS_OFF_SHELF)
from .tables.sqlcli import AsyncSessionLocal
from utils.common.enumTaskType import SourceTypeEnum
from .shelf_orm import is_off_shelf
# PluginUnavailableError 定义在 custom_plugin_orm（resolve_runtime_config 抛的就是它），
# 此处 re-export 供 modules/stream 统一捕获——两处必须是同一个异常类。
from .custom_plugin_orm import (resolve_runtime_config, assert_custom_bindable,
                                PluginUnavailableError)
from utils.getLogs import LOG


def _is_custom_type(type: str) -> bool:
    return type in (SourceTypeEnum.TTS_CUSTOM.value, SourceTypeEnum.ASR_CUSTOM.value,
                    SourceTypeEnum.LLM_CUSTOM.value)


# 基础类别 ↔ SourceList 绑定类型映射：会话解析时两类都要查（迁移前旧绑定
# 用 TTS/ASR/LLM，迁移后与新建绑定用 *_CUSTOM）
_SESSION_TYPES = {
    "tts": (SourceTypeEnum.TTS.value, SourceTypeEnum.TTS_CUSTOM.value),
    "asr": (SourceTypeEnum.ASR.value, SourceTypeEnum.ASR_CUSTOM.value),
    "llm": (SourceTypeEnum.LLM.value, SourceTypeEnum.LLM_CUSTOM.value),
}


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
    params: Union[dict, None]

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

async def _first_resource_id(session, model):
    """取某资源表「第一条」可用记录的 id。

    「第一条」按 id 升序取最小者（自增主键，即最早录入的一条），并跳过软删记录
    ——存量 is_delete 可能为 NULL，须 NULL 或 False 一并视为有效。
    表内无可用记录时返回 None，由调用方决定跳过。
    """
    row = await session.scalar(
        select(model.id).where(
            or_(model.is_delete.is_(None), model.is_delete.is_(False))
        ).order_by(model.id).limit(1)
    )
    return row


async def _bind_default_sources(session, tenant_id: int, owner_user_id: int = None) -> dict:
    """给新租户把 TTS / ASR / LLM / CHATTEMPLATE 各绑第一条并置为默认。

    建租户时调用，省掉后台手动逐条绑定 + 设默认的操作。每类型只绑一行且
    is_default=True，与 set_source_default 维持的「每类型至多一个默认」口径一致。
    某类型资源表为空时跳过该类型（不写脏绑定），结果在 bound 中如实反映。
    与 create_tenant 共用同一 session/事务：绑定失败则租户一起回滚，不留半成品。

    资源体系重构 + 严格私有的口径下，TTS/ASR/LLM 取**租户归属人自己的**个性插件
    （CustomPlugin.owner_id == owner_user_id，且基础插件在售）。归属人名下没有
    该类别的个性插件时跳过该类别——用户需先自建个性插件再绑（旧 Factories 行不
    再作为普通用户的可绑口径）。owner_user_id 为空（未归属租户/admin 直建）时，
    退化为「任一在售个性插件」保证新租户不至于完全无资源可跑。对话模板不变，
    仍绑 Factories 表。
    """
    bound = {}
    for source_type, model in (
        (SourceTypeEnum.TTS.value, TTSFactories),
        (SourceTypeEnum.ASR.value, ASRFactories),
        (SourceTypeEnum.LLM.value, LLMFactories),
        (SourceTypeEnum.CHATTEMPLATE.value, DigitalHumanChatTemplate),
    ):
        if source_type == SourceTypeEnum.CHATTEMPLATE.value:
            rid = await _first_resource_id(session, model)
            bind_type = source_type
        else:
            conds = [CustomPlugin.category == source_type,
                     or_(CustomPlugin.is_delete.is_(None), CustomPlugin.is_delete.is_(False)),
                     or_(BasePlugin.is_delete.is_(None), BasePlugin.is_delete.is_(False)),
                     func.coalesce(BasePlugin.status, STATUS_ACTIVE) != STATUS_OFF_SHELF]
            if owner_user_id is not None:
                conds.append(CustomPlugin.owner_id == owner_user_id)
            rid = await session.scalar(
                select(CustomPlugin.id)
                .join(BasePlugin, BasePlugin.id == CustomPlugin.base_plugin_id)
                .where(*conds)
                .order_by(CustomPlugin.id).limit(1))
            bind_type = SourceTypeEnum.to_custom(source_type)
        if rid is None:
            LOG(f"资源表 {model.__name__} 无可用记录，租户 {tenant_id} 跳过 {source_type} 自动绑定", "WARN")
            continue
        session.add(SourceList(tenant_id=tenant_id, type=bind_type,
                               reference_id=rid, is_default=True, is_delete=False))
        bound[source_type] = rid
    return bound


async def create_tenant(**kwargs):
    """创建租户，并自动把各类资源的第一条绑为默认。

    auto_bind_defaults=False 时跳过自动绑定（例如需要完全自定义资源初始化的场景）。
    """
    auto_bind = kwargs.pop("auto_bind_defaults", True)
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
            data = {"id": new_tenant.id}
            if auto_bind:
                data["default_sources"] = await _bind_default_sources(
                    session, new_tenant.id, owner_user_id=kwargs.get("user_id"))
            return GeneticResponse(data=data)


async def list_tenants(user_id: int = None):
    """租户列表。user_id 为空表示不限归属（管理员看全部），否则只返回该管理用户名下的租户。

    软删过滤用 or_(NULL, False)：存量 is_delete 可能为 NULL，
    原先的 filter_by(is_delete=False) 会漏掉这些行。
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Tenant).where(
            or_(Tenant.is_delete.is_(None), Tenant.is_delete.is_(False)))
        if user_id is not None:
            stmt = stmt.where(Tenant.user_id == user_id)
        tenants = await session.scalars(stmt)
        return [_TenantDetail.model_validate(t).model_dump() for t in tenants]


async def is_tenant_owned(tenant_id: int, user_id: int) -> bool:
    """租户是否属于该管理员（Tenant.user_id 直配，无外键，应用层校验）。

    user_id 为 NULL 的未归属租户对非管理员一律不可见、不可操作。
    """
    if user_id is None:
        return False
    async with AsyncSessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant).filter_by(id=tenant_id, user_id=user_id).where(
                or_(Tenant.is_delete.is_(None), Tenant.is_delete.is_(False)))
        )
        return tenant is not None


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

async def bind_source(tenant_id: int, type: str, reference_id: int,
                      admin: bool = False, user_id: int = None):
    """把一条资源（SourceList 行）绑定到租户。

    同一 (type, reference_id, tenant_id) 已存在时直接返回成功（幂等），
    避免重复绑定产生脏数据。

    类型口径（资源体系重构后）：
      - 普通用户（admin=False）只能绑 CHATTEMPLATE 与 *_CUSTOM（个性插件，
        严格私有——仅自己创建的）；旧的 TTS/ASR/LLM 直绑入口对普通用户关闭。
      - admin 保留旧类型直绑能力（存量运维兜底），新配置一律建议走个性插件。
      - *_CUSTOM 走 custom_plugin_orm 的可用性+可见性校验（基础插件下架即不可绑）。
      - 旧 TTS/ASR/LLM 类型保留给存量数据与内部迁移使用：已下架禁止新增绑定
        （下架语义=关闭增量入口，存量不受影响，见 shelf_orm.py）。
    """
    if not admin:
        if type not in (SourceTypeEnum.CHATTEMPLATE.value,) and not _is_custom_type(type):
            return GeneticResponse(code=400, msg="普通用户仅可绑定个性插件与对话模板")
    if _is_custom_type(type):
        denied = await assert_custom_bindable(type, reference_id, admin, user_id)
        if denied:
            return denied
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(
                select(Tenant).filter_by(id=tenant_id, is_delete=False))
            if not tenant:
                return GeneticResponse(code=400, msg="租户不存在")
            if not _is_custom_type(type) and await is_off_shelf(type, reference_id):
                return GeneticResponse(code=400, msg="该资源已下架，不可绑定")
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
    """列出租户已绑定的资源，并带上资源描述与上下架状态。

    资源信息直接 join 四张资源表取回，不再依赖前端拿资源池二次匹配——因为
    非 admin 的资源池列表已过滤掉下架资源，若这里只返 reference_id，
    「已绑定但被下架」的存量资源会显示成"未在资源池"且丢失下架提示。
    资源行已被物理删除（正常不会，删除是软删）时字段回落 None。
    status 为 NULL 归一为 active。
    """
    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(SourceList).filter_by(tenant_id=tenant_id).where(
                or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False))))
        rows = list(rows)

        # 按类型分组收集 reference_id，逐表批量取回描述与状态，避免逐行查询
        ids_by_type = {}
        for s in rows:
            ids_by_type.setdefault(s.type, set()).add(s.reference_id)

        # type -> {rid: {"desc":..., "tag":..., "voice":..., "module_path":..., "status":...}}
        info = {}
        model_fields = {
            SourceTypeEnum.TTS.value: (TTSFactories, ("desc", "tag", "voice")),
            SourceTypeEnum.ASR.value: (ASRFactories, ("desc",)),
            SourceTypeEnum.LLM.value: (LLMFactories, ("desc",)),
            SourceTypeEnum.CHATTEMPLATE.value: (DigitalHumanChatTemplate, ("desc", "module_path")),
        }
        for stype, rids in ids_by_type.items():
            entry = model_fields.get(stype)
            if not entry or not rids:
                continue
            model, fields = entry
            found = await session.scalars(select(model).where(model.id.in_(rids)))
            m = {}
            for obj in found:
                d = {f: getattr(obj, f, None) for f in fields}
                d["status"] = obj.status or "active"
                m[obj.id] = d
            info[stype] = m

        # 个性插件（*_CUSTOM）：desc 取插件描述/名称；可用性 = 自身未删 且
        # 基础插件存在、未删、在售——不满足即标 off_shelf（前端展示下架标签）。
        # 运行时对这类绑定直接拒绝会话（resolve_runtime_config 返回 None）。
        for stype, rids in ids_by_type.items():
            if not _is_custom_type(stype) or not rids:
                continue
            found = await session.execute(
                select(CustomPlugin, BasePlugin)
                .outerjoin(BasePlugin, BasePlugin.id == CustomPlugin.base_plugin_id)
                .where(CustomPlugin.id.in_(rids)))
            m = {}
            for c, base in found.all():
                base_ok = (base is not None and not base.is_delete and
                           (base.status or STATUS_ACTIVE) != STATUS_OFF_SHELF)
                avail = (not c.is_delete) and base_ok
                m[c.id] = {"desc": c.desc or c.name,
                           "status": STATUS_ACTIVE if avail else STATUS_OFF_SHELF}
            info[stype] = m

        result = []
        for s in rows:
            item = info.get(s.type, {}).get(s.reference_id, {})
            result.append({"id": s.id, "type": s.type, "reference_id": s.reference_id,
                           "is_default": bool(s.is_default),
                           "desc": item.get("desc"), "tag": item.get("tag"),
                           "voice": item.get("voice"), "module_path": item.get("module_path"),
                           "status": item.get("status")})
        return result


async def set_source_default(tenant_id: int, type: str, reference_id: int,
                             admin: bool = False, user_id: int = None):
    """把租户某类型下的指定绑定设为默认。

    同 (tenant_id, type) 下其余绑定 is_default 归零，仅目标为 1，
    保证每类型至多一个默认。对 TTS/ASR/LLM/CHATTEMPLATE 及 *_CUSTOM 通用。
    沿用 save_default_source_config 的写法：SourceList.is_default 直接置 1。

    个性插件（*_CUSTOM）用 assert_custom_bindable 校验可用性与可见性
    （基础插件下架即不可设默认）；旧资源沿用 is_off_shelf 检查。
    """
    if _is_custom_type(type):
        denied = await assert_custom_bindable(type, reference_id, admin, user_id)
        if denied:
            return denied
    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant_id, type=type).where(
                    or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False))))
            rows = list(rows)
            target = next((r for r in rows if r.reference_id == reference_id), None)
            if not target:
                return GeneticResponse(code=400, msg="绑定关系不存在")
            # 已下架资源不可新设为默认：默认资源是终端不下发 source_config 时的兜底，
            # 不应指向一个已停止供给的资源（存量默认不在此列，管理员可继续手动改）。
            if not _is_custom_type(type) and await is_off_shelf(type, reference_id):
                return GeneticResponse(code=400, msg="该资源已下架，不可设为默认")
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

            legacy_models = {"LLM": LLMFactories, "TTS": TTSFactories, "ASR": ASRFactories}
            legacy_maps, custom_maps = {}, {}
            for category, model in legacy_models.items():
                ids = [s.reference_id for s in sources
                       if s.type == SourceTypeEnum(category).value]
                if ids:
                    rows = await session.scalars(select(model).where(model.id.in_(ids)))
                    legacy_maps[category] = {r.id: r for r in rows}
                cids = [s.reference_id for s in sources
                        if s.type == SourceTypeEnum.to_custom(category)]
                if cids:
                    rows = await session.scalars(
                        select(CustomPlugin).where(CustomPlugin.id.in_(cids)))
                    custom_maps[category] = {r.id: r for r in rows}

            llm_list, tts_list, asr_list = [], [], []
            buckets = {"LLM": llm_list, "TTS": tts_list, "ASR": asr_list}
            for s in sources:
                category = SourceTypeEnum.to_base(s.type)
                if category not in buckets:
                    continue
                if _is_custom_type(s.type):
                    c = custom_maps.get(category, {}).get(s.reference_id)
                    # 终端资源列表口径：个性插件须自身未删且基础插件在售，否则不展示
                    if c is None or c.is_delete:
                        continue
                    base = await session.scalar(select(BasePlugin).filter_by(id=c.base_plugin_id))
                    if (not base or base.is_delete or
                            (base.status or STATUS_ACTIVE) == STATUS_OFF_SHELF):
                        continue
                    buckets[category].append({"id": c.id, "type": base.name, "desc": c.desc or c.name})
                    continue
                info = legacy_maps.get(category, {}).get(s.reference_id)
                if info:
                    model_cls = {"LLM": _GetLLMList, "TTS": _GetTTSList, "ASR": _GetASRList}[category]
                    buckets[category].append(model_cls.model_validate(info).model_dump())

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


async def _resolve_session_config(session, category: str, defaults: dict, given_id):
    """解析单类别（TTS/ASR/LLM）的会话配置，返回与 _Get*List2 同形的 dict。

    取值优先级：客户端 source_config 显式指定的 id > 租户默认绑定 > id=1 兜底。
    id 落在个性插件还是旧 Factories 的判定：先按 CustomPlugin 查（类别匹配即为
    个性插件）——
      - 是个性插件：resolve_runtime_config 返回可用配置；若其自身已删或基础插件
        已删/已下架则抛 PluginUnavailableError（严格全面禁用，不做 id=1 兜底，
        由 websocket 建链处拒绝会话）。
      - 不是个性插件：走旧 Factories 行；资源已被删除时回落 id=1（历史兼容，
        原行为不变）。
    given_id 与默认绑定 id 都可能是两类 id；默认绑定优先按其自身 type 判定。
    """
    custom_type = SourceTypeEnum.to_custom(category)
    model = {"TTS": TTSFactories, "ASR": ASRFactories, "LLM": LLMFactories}[category]

    default_id = defaults.get(custom_type) or defaults.get(category)
    rid = given_id or default_id or 1

    async def _load_legacy(legacy_id):
        row = await session.scalar(select(model).filter_by(id=legacy_id))
        if row is None and legacy_id != 1:
            LOG(f"租户默认资源 {model.__name__}#{legacy_id} 不存在，回落 id=1", "WARN")
            row = await session.scalar(select(model).filter_by(id=1))
        if row is None:
            raise PluginUnavailableError(f"{category} 资源表无可用记录（id={legacy_id}）")
        cfg = {c.name: getattr(row, c.name, None) for c in model.__table__.columns}
        cfg["status"] = cfg.get("status") or STATUS_ACTIVE
        return cfg

    # id 归属判定：命中 CustomPlugin（类别匹配，不过滤 is_delete——已删的个性
    # 插件必须报错而不是误落旧表同号资源）即按个性插件解析；否则走旧 Factories。
    hit_custom = await session.scalar(
        select(CustomPlugin.id).where(CustomPlugin.id == rid,
                                      CustomPlugin.category == category))
    if hit_custom is not None:
        return await resolve_runtime_config(session, custom_type, rid)
    return await _load_legacy(rid)


async def get_source_config(**kwargs):
    """解析一次会话实际使用的 LLM / TTS / ASR / 对话模板。

    取值优先级：客户端 source_config 显式指定的 id > 租户在 SourceList 中的默认绑定
    > id=1 兜底。最后一级只为兼容从未配置过默认资源的历史终端，避免直接中断会话。

    个性插件（*_CUSTOM 绑定或个性插件 id）走 resolve_runtime_config；
    基础插件下架/注销时抛 PluginUnavailableError，调用方（websocket）拒绝会话。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            defaults = await _tenant_default_source_ids(session, kwargs.get("uid"))

            tts_config = await _resolve_session_config(
                session, "TTS", defaults, kwargs.get("tts_id"))
            asr_config = await _resolve_session_config(
                session, "ASR", defaults, kwargs.get("asr_id"))
            llm_config = await _resolve_session_config(
                session, "LLM", defaults, kwargs.get("llm_id"))
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


def _terminal_safe_config(cfg: dict) -> dict:
    """安卓终端兼容（2026-10-23）：getDefaultSourceConfig 的返回值直接进旧终端
    （App 源码不动），其 UI 绑定按非空字符串解析 desc、按对象解析 params。
    个性插件允许 desc 留空，这里统一兜底：desc=None → 插件名（无名时空串）、
    params=None → {}。键集合保持 _Get*List2 原样，不增不减。
    """
    if cfg is None:
        return cfg
    if cfg.get("desc") is None:
        cfg["desc"] = cfg.get("name") or ""
    if cfg.get("params") is None:
        cfg["params"] = {}
    cfg.pop("name", None)  # 键集与旧接口严格一致（name 仅内部兜底用）
    return cfg


async def get_default_source_config(tenantname: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).filter_by(tenantname=tenantname))
            if not tenant:
                return None
            sources = await session.scalars(
                select(SourceList).filter_by(tenant_id=tenant.id, is_default=True).where(
                    or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False)))
                .order_by(SourceList.id)
            )
            result = {"llm_config": None, "tts_config": None, "asr_config": None}
            legacy_models = {"LLM": LLMFactories, "TTS": TTSFactories, "ASR": ASRFactories}
            for s in sources:
                category = SourceTypeEnum.to_base(s.type)
                if category not in legacy_models:
                    continue
                slot = f"{category.lower()}_config"
                if _is_custom_type(s.type):
                    # 个性插件默认：不可用（下架/删除）时如实返回 None，
                    # 终端据此提示更换资源，不会拿到旧数据继续跑
                    try:
                        cfg = await resolve_runtime_config(session, s.type, s.reference_id)
                    except PluginUnavailableError:
                        cfg = None
                    result[slot] = _terminal_safe_config(cfg)
                else:
                    row = await session.scalar(
                        select(legacy_models[category]).filter_by(id=s.reference_id))
                    result[slot] = _terminal_safe_config(
                        (_GetLLMList.model_validate(row).model_dump()
                         if category == "LLM" and row else
                         _GetTTSList.model_validate(row).model_dump()
                         if category == "TTS" and row else
                         _GetASRList.model_validate(row).model_dump() if row else None))
            return result


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
            session_types = {SourceTypeEnum.LLM.value, SourceTypeEnum.TTS.value, SourceTypeEnum.ASR.value,
                             SourceTypeEnum.LLM_CUSTOM.value, SourceTypeEnum.TTS_CUSTOM.value,
                             SourceTypeEnum.ASR_CUSTOM.value}
            for s in sources:
                if s.type in session_types:
                    s.is_default = False
                    session.add(s)
            for _type, id_key in ((SourceTypeEnum.LLM.value, "llm_id"),
                                  (SourceTypeEnum.TTS.value, "tts_id"),
                                  (SourceTypeEnum.ASR.value, "asr_id")):
                rid = kwargs.get(id_key)
                if rid is None:
                    continue
                # 迁移后租户的绑定行是 *_CUSTOM；旧终端仍按旧类型名传 id。
                # 两种 type 都找一遍，命中哪个设哪个为默认。
                source = await session.scalar(
                    select(SourceList).where(
                        SourceList.tenant_id == tenant.id,
                        SourceList.reference_id == rid,
                        SourceList.type.in_((_type, SourceTypeEnum.to_custom(_type)))))
                if source:
                    source.is_default = 1
                    session.add(source)
            return 1
