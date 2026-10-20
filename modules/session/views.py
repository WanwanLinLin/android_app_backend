from . import schema
from fastapi import APIRouter, status, Depends
from mybatisPlus.agent_orm import get_session_list, get_one_session
from mybatisPlus.tenant_orm import list_tenants
from utils.common.schema import GeneticResponse
from utils.admin_auth import current_admin, is_admin

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 会话记录是终端用户聊天审计数据（敏感）：一律需登录；
# 非 admin 角色只能看自己名下租户的会话（tenant_ids 收窄，详情逐条校验归属）。

@router.get("/v1/session/list", summary="会话记录分页列表", tags=["对话记录"])
async def _list_sessions(info: schema.SessionQuery = Depends(),
                         admin: dict = Depends(current_admin)):
    """按租户/时间范围分页查询会话。admin 全量；普通管理员仅限名下租户。"""
    if not is_admin(admin):
        owned = [t["id"] for t in await list_tenants(user_id=admin["id"])]
        if info.tenant_id is not None and info.tenant_id not in owned:
            return GeneticResponse(code=403, msg="无权查看该租户的对话记录")
        tenant_ids = owned
    else:
        tenant_ids = [info.tenant_id] if info.tenant_id is not None else None
    data = await get_session_list(tenant_ids=tenant_ids, start=info.start, end=info.end,
                                  page=info.page, size=info.size)
    return GeneticResponse(data=data)


@router.get("/v1/session/get/{id}", summary="会话详情（含聊天记录）", tags=["对话记录"])
async def _get_session(id: int, admin: dict = Depends(current_admin)):
    data = await get_one_session(id)
    if not data:
        return GeneticResponse(code=400, msg="data not exist")
    if not is_admin(admin):
        owned = {t["id"] for t in await list_tenants(user_id=admin["id"])}
        if data.get("tenant_id") not in owned:
            return GeneticResponse(code=403, msg="无权查看该租户的对话记录")
    return GeneticResponse(data=data)
