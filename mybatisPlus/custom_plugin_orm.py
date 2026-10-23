"""个性插件数据访问层——用户在基础插件之上定义的**私有**配置。

可见性规则（2026-10-22 起：严格私有，取消"平台归属/共享"概念）：
  - 普通用户：仅可见、可改、可删、可绑**自己创建**（owner_id == 自己）的个性插件；
  - admin：列表可见全部（用于评估基础插件下架影响），但不代改/代删别人的私有插件，
    也不能绑定别人的私有插件到自己租户；
  - 所属基础插件已下架/已删除的个性插件：对所有人不可见、不可绑定，
    已绑定租户运行时也直接拒绝（严格全面禁用）。

存量说明：旧资源池（Factories）迁移而来的插件已全部归属 hopesen（owner_id=1），
不再是 owner_id=NULL 的共享行。

自带配置语义：config 是完整配置（创建时从基础插件 default_config 预填、用户改定），
运行时直接交给 provider，基础插件后续修改不影响个性插件。provider 文件名写入
config 的 type 字段（TTS 另写 tag），沿用 modules/stream 的 importlib 链路。
"""
from sqlalchemy import func, or_, select

from utils.common.schema import GeneticResponse
from utils.common.enumTaskType import SourceTypeEnum
from .tables.industrial_park import (BasePlugin, CustomPlugin, SourceList, STATUS_ACTIVE,
                                     STATUS_OFF_SHELF)
from .tables.sqlcli import AsyncSessionLocal


def _alive(m):
    """有效记录：is_delete 为 NULL 与 False 都算有效（本项目历史数据口径）。"""
    return or_(m.is_delete.is_(None), m.is_delete.is_(False))


# 个性插件 config 必含键模板（2026-10-22 起编辑/创建保存时的校验依据）：
#   TTS: url | tag | voice | apikey | params
#   ASR / LLM: url | apikey | params
# 允许多余键（provider 私有参数）；键值允许为 null（如 params 无附加参数），
# 但键本身必须存在。type 为运行时 import 目标，由基础插件名强制写入，
# 不属于用户可编辑键，故不在模板内。
CONFIG_TEMPLATE = {
    "TTS": ("url", "tag", "voice", "apikey", "params"),
    "ASR": ("url", "apikey", "params"),
    "LLM": ("url", "apikey", "params"),
}


def validate_config_template(category: str, config: dict):
    """按类别模板校验 config：返回 None=通过，否则返回缺失键的提示文案。"""
    required = CONFIG_TEMPLATE.get(category)
    if required is None:
        return None
    if not isinstance(config, dict):
        return "config 必须是 JSON 对象"
    missing = [k for k in required if k not in config]
    if missing:
        return (f"{category} 个性插件配置缺少必含参数：{' | '.join(missing)}"
                f"（模板要求：{' | '.join(required)}）")
    return None


def _base_alive_cond():
    """「所属基础插件未删除」的 where 条件（在售条件另行叠加，见列表函数）。"""
    return or_(BasePlugin.is_delete.is_(None), BasePlugin.is_delete.is_(False))


def _serialize(c: CustomPlugin, base=None) -> dict:
    return {"id": c.id, "name": c.name, "category": c.category,
            "base_plugin_id": c.base_plugin_id,
            "base_plugin_name": base.name if base else None,
            "desc": c.desc, "config": c.config, "owner_id": c.owner_id,
            "create_time": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else None,
            "update_time": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else None}


async def get_custom_plugin_list(category: str, admin: bool, user_id: int):
    """按类别列个性插件。严格私有：普通用户仅见自己的；
    admin 见全部（仅用于治理/下架影响评估，改删绑仍限本人）。
    且所属基础插件必须未删除并在售。
    """
    async with AsyncSessionLocal() as session:
        stmt = (select(CustomPlugin, BasePlugin)
                .join(BasePlugin, BasePlugin.id == CustomPlugin.base_plugin_id)
                .where(CustomPlugin.category == category, _alive(CustomPlugin),
                       _base_alive_cond(),
                       func.coalesce(BasePlugin.status, STATUS_ACTIVE) != STATUS_OFF_SHELF))
        if not admin:
            stmt = stmt.where(CustomPlugin.owner_id == user_id)
        rows = (await session.execute(stmt.order_by(CustomPlugin.id))).all()
        result = [_serialize(c, b) for c, b in rows]
        return {"rows": result, "total": len(result)}


async def get_visible_custom_ids(category: str, admin: bool, user_id: int):
    """当前用户「可绑定」的个性插件 id 集合——严格私有，仅自己创建的。"""
    async with AsyncSessionLocal() as session:
        stmt = (select(CustomPlugin.id)
                .join(BasePlugin, BasePlugin.id == CustomPlugin.base_plugin_id)
                .where(CustomPlugin.category == category, _alive(CustomPlugin),
                       _base_alive_cond(),
                       func.coalesce(BasePlugin.status, STATUS_ACTIVE) != STATUS_OFF_SHELF,
                       CustomPlugin.owner_id == user_id))
        return set((await session.scalars(stmt)).all())


async def get_one_custom_plugin(id: int):
    async with AsyncSessionLocal() as session:
        c = await session.scalar(select(CustomPlugin).filter_by(id=id))
        if not c or c.is_delete:
            return None
        base = await session.scalar(select(BasePlugin).filter_by(id=c.base_plugin_id))
        return _serialize(c, base)


class PluginUnavailableError(Exception):
    """个性插件在运行时不可用（自身已删 / 基础插件已删或已下架）。

    严格全面禁用的落点：websocket 建链处捕获后向终端报错并断连，
    不会带着不可用配置继续会话。
    """


async def resolve_runtime_config(session, custom_type: str, reference_id: int):
    """运行时解析（用调用方 session）：个性插件 id → 可直接喂给 provider 的配置 dict。

    custom_type 取 *_CUSTOM；返回 dict 的键对齐 tenant_orm 的 _Get*List2
    （id/type/url/apikey/params/tag/voice/desc）。
    2026-10-22 起 TTS 参数键统一为 params（原 additional_param 已改名）。
    严格全面禁用：插件存在但已删、或基础插件已删/已下架 → 抛 PluginUnavailableError
    （运行时据此拒绝会话）；该 id 根本不是个性插件 → 返回 None（调用方回落旧
    Factories 通路，兼容未迁移终端传的旧资源 id）。
    """
    category = SourceTypeEnum.to_base(custom_type)
    c = await session.scalar(select(CustomPlugin).filter_by(id=reference_id))
    if not c or c.category != category:
        return None
    if c.is_delete:
        raise PluginUnavailableError(f"个性插件 #{reference_id} 已被删除")
    base = await session.scalar(select(BasePlugin).filter_by(id=c.base_plugin_id))
    if not base or base.is_delete:
        raise PluginUnavailableError(
            f"个性插件 #{reference_id}（{c.name}）的基础插件已被注销")
    if (base.status or STATUS_ACTIVE) == STATUS_OFF_SHELF:
        raise PluginUnavailableError(
            f"个性插件 #{reference_id}（{c.name}）的基础插件 {base.name} 已下架")
    # config 自带完整配置；type 恒以基础插件名为准（importlib 目标文件），
    # 防止用户改 config 里的 type 指向任意模块。
    # TTS 的 tag（真正的 import 目标）2026-10-22 起允许用户编辑，但保存时已校验
    # 必须是登记在册且在售的 TTS 基础插件名；缺省时回落基础插件名。
    cfg = dict(c.config or {})
    cfg["type"] = base.name
    if category == "TTS" and not cfg.get("tag"):
        cfg["tag"] = base.name
    cfg["id"] = c.id
    cfg["desc"] = c.desc
    # 键位补齐：与 Factories 行同形（_Get*List2 的键），provider 按 get 取值不踩空
    for k in ("url", "apikey", "params", "voice", "tag"):
        cfg.setdefault(k, None)
    return cfg


async def is_custom_available(custom_type: str, reference_id: int) -> bool:
    """个性插件当前是否可用（存在、未删、基础插件在售）——绑定/设默认前置校验。"""
    try:
        async with AsyncSessionLocal() as session:
            return (await resolve_runtime_config(session, custom_type, reference_id)) is not None
    except PluginUnavailableError:
        return False


async def assert_custom_bindable(custom_type: str, reference_id: int, admin: bool, user_id: int):
    """绑定/设默认前置检查：通过返回 None，否则返回拒绝响应。

    严格私有：普通用户只能绑自己创建的可用个性插件（未删、基础在售）。
    admin 为租户治理superuser，可绑任意「可用」个性插件（不限归属）。
    """
    try:
        async with AsyncSessionLocal() as session:
            cfg = await resolve_runtime_config(session, custom_type, reference_id)
            if cfg is None:
                return GeneticResponse(code=400, msg="个性插件不存在")
            c = await session.scalar(select(CustomPlugin).filter_by(id=reference_id))
    except PluginUnavailableError as e:
        return GeneticResponse(code=400, msg=str(e))
    if not admin and c.owner_id != user_id:
        return GeneticResponse(code=403, msg="只能绑定自己创建的个性插件")
    return None


async def _valid_tts_tag(session, tag) -> bool:
    """TTS 的 tag 是运行时 import 目标：必须是已登记、未删除且在售的 TTS 基础插件名。"""
    if not isinstance(tag, str) or not tag.strip():
        return False
    hit = await session.scalar(
        select(BasePlugin.id)
        .where(BasePlugin.category == "TTS", BasePlugin.name == tag.strip(),
               _alive(BasePlugin),
               func.coalesce(BasePlugin.status, STATUS_ACTIVE) != STATUS_OFF_SHELF))
    return hit is not None


async def create_custom_plugin(admin: bool, user_id: int, **kwargs):
    """创建个性插件（所有登录用户）。严格私有：owner_id 恒为创建者本人。

    - base_plugin_id 必须指向一个存在、未删除且在售的基础插件；
    - config 为完整自带配置，按 CONFIG_TEMPLATE 校验必含键
      （TTS: url|tag|voice|apikey|params；ASR/LLM: url|apikey|params）；
    - type 恒为基础插件名（importlib 目标，用户不可指定）；TTS 的 tag 缺省
      写基础插件名，用户显式指定时必须是登记在册且在售的 TTS 基础插件名；
    - 不再有"平台归属/共享"插件（platform_owned 已废弃，忽略该入参）。
    """
    base_id = kwargs.get("base_plugin_id")
    name = (kwargs.get("name") or "").strip()
    config = kwargs.get("config")
    if not name:
        return GeneticResponse(code=400, msg="插件名称不能为空")
    if not isinstance(config, dict):
        return GeneticResponse(code=400, msg="config 必须是 JSON 对象")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            base = await session.scalar(select(BasePlugin).filter_by(id=base_id))
            if not base or base.is_delete:
                return GeneticResponse(code=400, msg="基础插件不存在")
            if (base.status or STATUS_ACTIVE) == STATUS_OFF_SHELF:
                return GeneticResponse(code=400, msg="基础插件已下架，不可基于它创建个性插件")
            cfg = dict(config)
            cfg.pop("id", None)
            if base.category == "TTS":
                user_tag = cfg.get("tag")
                if user_tag in (None, ""):
                    cfg["tag"] = base.name
                elif not await _valid_tts_tag(session, user_tag):
                    return GeneticResponse(
                        code=400,
                        msg=f"tag「{user_tag}」不是登记在册且在售的 TTS 基础插件，不可作为运行目标")
            err = validate_config_template(base.category, cfg)
            if err:
                return GeneticResponse(code=400, msg=err)
            cfg["type"] = base.name
            plugin = CustomPlugin(name=name, category=base.category, base_plugin_id=base.id,
                                  desc=kwargs.get("desc"), config=cfg,
                                  owner_id=user_id, is_delete=False)
            session.add(plugin)
            await session.flush()
            return GeneticResponse(data={"id": plugin.id})


async def update_custom_plugin(id: int, admin: bool, user_id: int, **kwargs):
    """更新个性插件（整个 config 可编辑）。

    严格私有：**只有创建者本人**（owner_id==自己）能改；别人的插件（含 admin）
    一律不能代改。

    2026-10-22 起编辑面为**完整 config**（url/apikey/voice/params 等均可改），
    保存时按 CONFIG_TEMPLATE 做模板校验：
      - TTS 必含 url | tag | voice | apikey | params；ASR / LLM 必含 url | apikey | params；
      - TTS 的 tag 是运行时 import 目标，必须是登记在册且在售的 TTS 基础插件名；
      - type 恒为基础插件名（防注入任意模块），用户传入的 type 会被覆盖；
      - 允许多余键（provider 私有参数）；键值允许为 null，但键必须存在。
    kwargs 中的 name/desc/base_plugin_id 忽略（名称与归属不可改）。
    """
    config = kwargs.get("config")
    if config is None:
        return GeneticResponse(code=400, msg="请提供要修改的 config（JSON 对象）")
    if not isinstance(config, dict):
        return GeneticResponse(code=400, msg="config 必须是 JSON 对象")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            c = await session.scalar(select(CustomPlugin).filter_by(id=id))
            if not c or c.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            if c.owner_id != user_id:
                return GeneticResponse(code=403, msg="只能修改自己创建的个性插件")
            cfg = dict(config)
            cfg.pop("id", None)
            if c.category == "TTS":
                user_tag = cfg.get("tag")
                if user_tag in (None, ""):
                    base = await session.scalar(select(BasePlugin).filter_by(id=c.base_plugin_id))
                    cfg["tag"] = base.name if base else None
                elif not await _valid_tts_tag(session, user_tag):
                    return GeneticResponse(
                        code=400,
                        msg=f"tag「{user_tag}」不是登记在册且在售的 TTS 基础插件，不可作为运行目标")
            err = validate_config_template(c.category, cfg)
            if err:
                return GeneticResponse(code=400, msg=err)
            base = await session.scalar(select(BasePlugin).filter_by(id=c.base_plugin_id))
            cfg["type"] = base.name if base else cfg.get("type")
            c.config = cfg  # JSON 列整体替换，确保 SQLAlchemy 感知变更
            session.add(c)
            return GeneticResponse()


async def delete_custom_plugin(id: int, admin: bool, user_id: int):
    """删除个性插件（软删）：严格私有，**仅创建者本人**可删（admin 不代删别人的）。
    仍有租户绑定则拒绝（防 SourceList 悬空）。"""
    custom_type = None
    async with AsyncSessionLocal() as session:
        async with session.begin():
            c = await session.scalar(select(CustomPlugin).filter_by(id=id))
            if not c or c.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            if c.owner_id != user_id:
                return GeneticResponse(code=403, msg="只能删除自己创建的个性插件")
            custom_type = SourceTypeEnum.to_custom(c.category)
            cnt = await session.scalar(
                select(func.count()).select_from(SourceList)
                .where(SourceList.type == custom_type, SourceList.reference_id == id)
                .where(_alive(SourceList)))
            if cnt:
                return GeneticResponse(code=400, msg=f"仍有 {cnt} 个租户绑定该个性插件，请先解绑")
            c.is_delete = True
            session.add(c)
            return GeneticResponse()
