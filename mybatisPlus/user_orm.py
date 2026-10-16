"""后台管理员（User）数据访问层。

架构调整后，User 仅承担两件事：
  1. 登录鉴权（get_password）
  2. Tenant 的生命周期管理入口（实际数据落在 Tenant 表，见 tenant_orm）

业务归属（资源列表、默认配置、agent 会话等）一律以 Tenant 为主体，
统一由 mybatisPlus.tenant_orm 提供，本模块不再涉及。
"""
from sqlalchemy import or_, select

from .tables.industrial_park import User
from .tables.sqlcli import AsyncSessionLocal


async def get_password(username: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await session.scalar(select(User).filter_by(username=username))
            if not user:
                return None
            return user.hashed_password


async def get_admin(username: str):
    """按用户名取有效管理员。软删过滤用 or_(NULL, False)：
    存量 is_delete 可能为 NULL，filter_by(is_delete=False) 会漏掉这些行。"""
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).filter_by(username=username).where(
                or_(User.is_delete.is_(None), User.is_delete.is_(False)))
        )
        if not user:
            return None
        return {"id": user.id, "username": user.username, "role": user.role,
                "nickname": user.nickname}


async def list_admins():
    """管理员账号精简列表（id/username/nickname/role），供前端下拉选择。

    存量 is_delete 可能为 NULL，NULL 或 False 视为有效。
    """
    async with AsyncSessionLocal() as session:
        users = await session.scalars(
            select(User).where(or_(User.is_delete.is_(None), User.is_delete.is_(False)))
        )
        return [{"id": u.id, "username": u.username, "nickname": u.nickname,
                 "role": u.role} for u in users]
