"""后台管理员（User）数据访问层。

架构调整后，User 仅承担两件事：
  1. 登录鉴权（get_password）
  2. Tenant 的生命周期管理入口（实际数据落在 Tenant 表，见 tenant_orm）

业务归属（资源列表、默认配置、agent 会话等）一律以 Tenant 为主体，
统一由 mybatisPlus.tenant_orm 提供，本模块不再涉及。
"""
from sqlalchemy import select

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
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).filter_by(username=username, is_delete=False)
        )
        if not user:
            return None
        return {"id": user.id, "username": user.username, "role": user.role,
                "nickname": user.nickname}
