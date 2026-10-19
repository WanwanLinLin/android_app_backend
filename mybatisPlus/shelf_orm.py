"""资源池上下架（off_shelf）数据访问层——四类资源通用。

设计要点（与 is_delete 语义严格分离）：
  - status = active（或 NULL）：在售，可绑定、可设默认
  - status = off_shelf：已下架，禁止新增绑定与设为默认，但**存量绑定照常可用**

为什么不做成删除：资源被 SourceList 按 reference_id 引用，租户还可能把它设为
默认资源（终端不下发 source_config 时直接使用）。若下架即软删，这些租户的会话
会当场失效。故下架只是「关闭增量入口」，绝不动引用完整性——SourceList 指向的
行永远存在。

判定下架必须写 status == 'off_shelf'，不能写 status != 'active'：
存量行该列可能为 NULL（迁移前数据），NULL 的语义是 active。

放本模块而非各 *_orm.py：下架要同时读资源表与 SourceList（跨表算影响面），
四类逻辑同构，重复四遍容易漂移。各模块 views 直接调本模块。
"""
from sqlalchemy import func, or_, select

from utils.common.schema import GeneticResponse
from utils.common.enumTaskType import SourceTypeEnum
from .tables.industrial_park import (ASRFactories, DigitalHumanChatTemplate,
                                     LLMFactories, SourceList, TTSFactories,
                                     Tenant, STATUS_ACTIVE, STATUS_OFF_SHELF)
from .tables.sqlcli import AsyncSessionLocal

# SourceList.type 取值 → 资源表模型
RESOURCE_MODELS = {
    SourceTypeEnum.TTS.value: TTSFactories,
    SourceTypeEnum.ASR.value: ASRFactories,
    SourceTypeEnum.LLM.value: LLMFactories,
    SourceTypeEnum.CHATTEMPLATE.value: DigitalHumanChatTemplate,
}

# 有效记录：本项目历史数据 is_delete 可能为 NULL，NULL 与 False 都算有效
_ALIVE = lambda m: or_(m.is_delete.is_(None), m.is_delete.is_(False))


def _model(type: str):
    return RESOURCE_MODELS.get(type)


def active_only(model):
    """列表过滤条件：排除已下架资源（供非 admin 角色的资源列表使用）。

    存量行 status 可能为 NULL，语义等同 active，故用 coalesce 兜底后再判
    != off_shelf，不能直接写 status != 'off_shelf'（NULL 参与比较恒为 NULL，
    会把在售的历史行误杀）。
    """
    return func.coalesce(model.status, STATUS_ACTIVE) != STATUS_OFF_SHELF


async def get_shelf_status(type: str, reference_id: int):
    """取单条资源的上下架状态，NULL 归一为 active。资源不存在返回 None。"""
    model = _model(type)
    if not model:
        return None
    async with AsyncSessionLocal() as session:
        row = await session.scalar(select(model).filter_by(id=reference_id))
        if not row:
            return None
        return row.status or STATUS_ACTIVE


async def is_off_shelf(type: str, reference_id: int) -> bool:
    """资源是否已下架（供 bind / setDefault 前置校验）。资源不存在视为未下架，
    由调用方原有的存在性校验负责报错，本函数不越权判断。"""
    return (await get_shelf_status(type, reference_id)) == STATUS_OFF_SHELF


async def list_bound_tenants(type: str, reference_id: int):
    """列出把该资源绑为可用资源的有效租户（含默认标记）。

    供下架影响面预览与删除前置检查复用。
    """
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(SourceList.tenant_id, SourceList.is_default, Tenant.tenantname)
            .outerjoin(Tenant, Tenant.id == SourceList.tenant_id)
            .filter(SourceList.type == type,
                    SourceList.reference_id == reference_id)
            .where(or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False)))
            .order_by(SourceList.tenant_id)
        )
        return [{"tenant_id": tid,
                 "tenantname": name or f"#{tid}",
                 "is_default": bool(dft)}
                for tid, dft, name in rows.all()]


async def off_shelf_preview(type: str, reference_id: int):
    """下架前的影响面：受影响租户清单 + 其中把它设为默认的数量。

    前端据此弹窗让管理员确认，避免在不知道影响谁的情况下盲下架。
    """
    model = _model(type)
    if not model:
        return GeneticResponse(code=400, msg="未知的资源类型")
    async with AsyncSessionLocal() as session:
        row = await session.scalar(select(model).filter_by(id=reference_id))
        if not row:
            return GeneticResponse(code=400, msg="data not exist")
    tenants = await list_bound_tenants(type, reference_id)
    default_tenants = [t for t in tenants if t["is_default"]]
    return GeneticResponse(data={
        "id": reference_id,
        "type": type,
        "status": row.status or STATUS_ACTIVE,
        "bound_count": len(tenants),
        "default_count": len(default_tenants),
        "tenants": tenants,
        # 前端提示文案的依据：有默认引用时下架后这些租户仍会用它的旧配置
        "warning": ("该资源已被设为默认，下架后这些租户的现有会话仍继续使用它，"
                    "直到管理员改设其他默认资源" if default_tenants else None),
    })


async def set_shelf_status(type: str, reference_id: int, status: str):
    """置上下架状态。status 只接受 active / off_shelf。

    下架不校验绑定数——允许停用正在被使用的资源（供应商下线、成本过高等是
    真实场景），影响面由 preview + 前端二次确认承担。上架无条件放行。
    """
    if status not in (STATUS_ACTIVE, STATUS_OFF_SHELF):
        return GeneticResponse(code=400, msg="非法的 status")
    model = _model(type)
    if not model:
        return GeneticResponse(code=400, msg="未知的资源类型")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            row = await session.scalar(select(model).filter_by(id=reference_id))
            if not row:
                return GeneticResponse(code=400, msg="data not exist")
            if (row.status or STATUS_ACTIVE) == status:
                return GeneticResponse(msg="状态未变化",
                                       data={"id": reference_id, "status": status})
            row.status = status
            session.add(row)
            return GeneticResponse(msg="已下架" if status == STATUS_OFF_SHELF else "已上架",
                                   data={"id": reference_id, "status": status})


async def binding_guard(type: str, reference_id: int, session=None):
    """删除前置检查：资源是否仍有有效绑定。有则返回拒绝响应，无则返回 None。

    删除与下架不同——删除会让 SourceList 引用悬空，租户配置直接失效，
    因此必须先解绑。用调用方传入的 session 以便与其删除操作同事务。
    """
    if not _model(type):
        return GeneticResponse(code=400, msg="未知的资源类型")

    async def _check(s):
        cnt = await s.scalar(
            select(func.count()).select_from(SourceList)
            .filter(SourceList.type == type,
                    SourceList.reference_id == reference_id)
            .where(or_(SourceList.is_delete.is_(None), SourceList.is_delete.is_(False)))
        )
        return cnt or 0

    if session is not None:
        cnt = await _check(session)
    else:
        async with AsyncSessionLocal() as s:
            cnt = await _check(s)
    if cnt:
        return GeneticResponse(code=400,
                               msg=f"该资源仍有 {cnt} 个租户绑定，请先解绑或改用下架")
    return None
