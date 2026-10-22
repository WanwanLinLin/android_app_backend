"""基础插件数据访问层——utils/providers/{tts,asr,llm} 代码插件的登记与上下架。

基础插件本体是磁盘代码文件（一个插件一个文件，排除 base.py / __init__.py），
本表只做「登记 + 元数据 + 上下架」，详见 tables.industrial_park.BasePlugin 注释。

与 shelf_orm 的关系：四类资源池（Factories/对话模板）的上下架沿用 shelf_orm；
基础插件的下架语义更严格（全面禁用，见下），且要连带计算「基于它的个性插件
及其租户绑定」的影响面，故独立成模块，不复用 shelf_orm。

下架语义（与资源池 off_shelf 的「存量照常可用」不同，这里是严格全面禁用）：
  - 普通用户在基础插件列表、个性插件列表里都看不到它和基于它的个性插件；
  - 个性插件不可新绑定，已绑定的租户在会话运行时也会被直接拒绝；
  - 重新上架后一切自动恢复（可见性/可用性是 join 计算的，没有落数据位）。
"""
from pathlib import Path

from sqlalchemy import func, or_, select

from utils.common.schema import GeneticResponse
from utils.common.enumTaskType import SourceTypeEnum
from .tables.industrial_park import (BasePlugin, CustomPlugin, SourceList, Tenant,
                                     STATUS_ACTIVE, STATUS_OFF_SHELF)
from .tables.sqlcli import AsyncSessionLocal

# 插件目录：<项目根>/utils/providers/<类别小写>
PROVIDERS_ROOT = Path(__file__).resolve().parents[1] / "utils" / "providers"
CATEGORIES = ("TTS", "ASR", "LLM")
_EXCLUDE_FILES = {"base.py", "__init__.py"}


def _alive(m):
    """有效记录：本项目历史数据 is_delete 可能为 NULL，NULL 与 False 都算有效。"""
    return or_(m.is_delete.is_(None), m.is_delete.is_(False))


def scan_plugins(category: str):
    """扫描插件目录，返回磁盘上可登记的插件文件名（不含 .py，排除 base/__init__）。"""
    d = PROVIDERS_ROOT / category.lower()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.py") if p.name not in _EXCLUDE_FILES)


async def sync_disk_plugins(session):
    """把磁盘上「有代码文件但登记表里没有」的插件自动登记为在售（用调用方事务）。

    列表接口每次先跑一遍，保证后台展示与目录一致；软删过的文件视为管理员
    主动注销，不会被自动重新登记（想恢复在列表里点「新增」重新登记即可）。
    """
    registered = {(c, n) for c, n in (await session.execute(
        select(BasePlugin.category, BasePlugin.name))).all()}
    added = 0
    for category in CATEGORIES:
        for name in scan_plugins(category):
            if (category, name) in registered:
                continue
            session.add(BasePlugin(category=category, name=name, status=STATUS_ACTIVE,
                                   desc=None, is_delete=False))
            added += 1
    # autoflush=False 的工程里必须显式 flush，否则同事务内后续 select 看不到
    # 刚登记的行（迁移脚本与列表接口的 custom_count join 都依赖这点）
    if added:
        await session.flush()
    return added


async def get_base_plugin_list(only_active: bool = False):
    """基础插件列表。only_active=True（非 admin）时过滤已下架项。

    附带 custom_count：基于该插件且仍有效的个性插件数量，供管理员评估下架影响。
    """
    results = []
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await sync_disk_plugins(session)
            stmt = select(BasePlugin).where(_alive(BasePlugin))
            if only_active:
                stmt = stmt.where(func.coalesce(BasePlugin.status, STATUS_ACTIVE) != STATUS_OFF_SHELF)
            plugins = (await session.scalars(stmt.order_by(BasePlugin.category, BasePlugin.id))).all()
            # 一次分组统计个性插件数，避免逐行查询
            counts = dict((await session.execute(
                select(CustomPlugin.base_plugin_id, func.count())
                .where(_alive(CustomPlugin))
                .group_by(CustomPlugin.base_plugin_id))).all())
            for p in plugins:
                results.append({
                    "id": p.id,
                    "category": p.category,
                    "name": p.name,
                    "desc": p.desc,
                    "default_config": p.default_config,
                    "status": p.status or STATUS_ACTIVE,
                    "custom_count": counts.get(p.id, 0),
                    "create_time": p.create_time.strftime("%Y-%m-%d %H:%M:%S") if p.create_time else None,
                    "update_time": p.update_time.strftime("%Y-%m-%d %H:%M:%S") if p.update_time else None,
                })
            return {"rows": results, "total": len(results)}


async def get_one_base_plugin(id: int):
    async with AsyncSessionLocal() as session:
        p = await session.scalar(select(BasePlugin).filter_by(id=id))
        if not p:
            return None
        return {"id": p.id, "category": p.category, "name": p.name, "desc": p.desc,
                "default_config": p.default_config, "status": p.status or STATUS_ACTIVE}


async def add_one_base_plugin(**kwargs):
    """登记一个磁盘上已存在的插件文件（管理员）。

    「新增」的边界：插件代码文件本身不能通过后台创建——管理员先把插件文件放进
    utils/providers/<类别>/，再在后台登记（或直接等列表扫描自动登记）。
    同名记录曾被软删（注销）时复活并覆盖元数据，避免登记表出现同键双行。
    """
    category = (kwargs.get("category") or "").upper()
    name = (kwargs.get("name") or "").strip()
    if category not in CATEGORIES:
        return GeneticResponse(code=400, msg="类别仅支持 TTS / ASR / LLM")
    if not name:
        return GeneticResponse(code=400, msg="插件名不能为空")
    if not (PROVIDERS_ROOT / category.lower() / f"{name}.py").is_file():
        return GeneticResponse(code=400,
                               msg=f"插件文件 utils/providers/{category.lower()}/{name}.py 不存在，"
                                   "请先放入代码文件再登记")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            exist = await session.scalar(
                select(BasePlugin).filter_by(category=category, name=name))
            if exist and not exist.is_delete:
                return GeneticResponse(code=400, msg="该插件已登记")
            if exist:  # 曾注销 → 复活并更新元数据
                exist.is_delete = False
                exist.status = STATUS_ACTIVE
                exist.desc = kwargs.get("desc")
                exist.default_config = kwargs.get("default_config")
                session.add(exist)
                return GeneticResponse(data={"id": exist.id, "reactivated": True})
            plugin = BasePlugin(category=category, name=name, desc=kwargs.get("desc"),
                                default_config=kwargs.get("default_config"),
                                status=STATUS_ACTIVE, is_delete=False)
            session.add(plugin)
            await session.flush()
            return GeneticResponse(data={"id": plugin.id})


async def update_one_base_plugin(id: int, **kwargs):
    """更新展示元数据（仅 desc）。category / name 与磁盘文件绑定，不允许改
    （改名=删除+重新登记）；default_config 登记后同样不再开放编辑——
    运行时参数只在个性插件层（config.params）修改。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            plugin = await session.scalar(select(BasePlugin).filter_by(id=id))
            if not plugin:
                return GeneticResponse(code=400, msg="data not exist")
            for k in ("desc",):
                if kwargs.get(k, None) is not None:
                    setattr(plugin, k, kwargs.get(k))
            session.add(plugin)
            return GeneticResponse()


async def get_custom_plugins_of_base(session, base_id: int):
    """基于该基础插件的全部有效个性插件（含隐藏归属，用于影响面与删除检查）。"""
    rows = await session.scalars(
        select(CustomPlugin).where(CustomPlugin.base_plugin_id == base_id).where(_alive(CustomPlugin)))
    return list(rows)


async def delete_one_base_plugin(id: int):
    """注销基础插件（软删 + 置下架）。

    仍有基于它的个性插件时拒绝删除——删除会让这些个性插件在运行时永远解析失败
    （连重新上架都救不回来）。确要下线请先处理个性插件，或仅做下架。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            plugin = await session.scalar(select(BasePlugin).filter_by(id=id))
            if not plugin or plugin.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            customs = await get_custom_plugins_of_base(session, id)
            if customs:
                return GeneticResponse(code=400,
                                       msg=f"仍有 {len(customs)} 个基于该插件的个性插件，"
                                           "请先删除这些个性插件，或改用下架")
            plugin.is_delete = True
            plugin.status = STATUS_OFF_SHELF
            session.add(plugin)
            return GeneticResponse()


async def set_base_shelf_status(id: int, status: str):
    """基础插件上下架。status 仅接受 active / off_shelf；下架为严格全面禁用。"""
    if status not in (STATUS_ACTIVE, STATUS_OFF_SHELF):
        return GeneticResponse(code=400, msg="非法的 status")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            plugin = await session.scalar(select(BasePlugin).filter_by(id=id))
            if not plugin or plugin.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            if (plugin.status or STATUS_ACTIVE) == status:
                return GeneticResponse(msg="状态未变化", data={"id": id, "status": status})
            plugin.status = status
            session.add(plugin)
            return GeneticResponse(msg="已下架" if status == STATUS_OFF_SHELF else "已上架",
                                   data={"id": id, "status": status})


async def base_off_shelf_preview(id: int):
    """下架影响面：基于该插件的个性插件清单 + 各插件被哪些租户绑定。

    严格下架会当场切断这些租户的会话（运行时直接拒绝），影响面比资源池下架大，
    前端必须弹窗让管理员确认。
    """
    async with AsyncSessionLocal() as session:
        plugin = await session.scalar(select(BasePlugin).filter_by(id=id))
        if not plugin or plugin.is_delete:
            return GeneticResponse(code=400, msg="data not exist")
        customs = await get_custom_plugins_of_base(session, id)
        custom_type = SourceTypeEnum.to_custom(plugin.category)
        tenants = []
        if customs:
            custom_ids = [c.id for c in customs]
            rows = await session.execute(
                select(SourceList.reference_id, func.count(), func.max(Tenant.tenantname))
                .outerjoin(Tenant, Tenant.id == SourceList.tenant_id)
                .where(SourceList.type == custom_type,
                       SourceList.reference_id.in_(custom_ids))
                .where(_alive(SourceList))
                .group_by(SourceList.reference_id)
            )
            bound_map = {rid: cnt for rid, cnt, _ in rows.all()}
        else:
            bound_map = {}
        return GeneticResponse(data={
            "id": id,
            "category": plugin.category,
            "name": plugin.name,
            "status": plugin.status or STATUS_ACTIVE,
            "custom_count": len(customs),
            "customs": [{"id": c.id, "name": c.name, "desc": c.desc,
                         "owner_id": c.owner_id,
                         "bound_count": bound_map.get(c.id, 0)} for c in customs],
            "bound_count": sum(bound_map.values()),
            "warning": ("该插件下架后，基于它的个性插件对普通用户不可见、不可绑定，"
                        "已绑定租户的会话运行时将被直接拒绝（严格下架，与资源池的存量保留语义不同）"
                        if customs else None),
        })
