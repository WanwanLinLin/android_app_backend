# -*- coding：utf-8 -*-
"""账号级 API Key 数据访问层（UserApiKey）。

Key 归属后台账号（User.id），模块无关：知识库等模块的开放接口统一以
key 归属者身份判定数据范围。约定与其余 *_orm 一致：全部 async、返回
dict 或 GeneticResponse；is_delete 历史可能为 NULL，过滤一律兼容 NULL；
不使用数据库外键。
"""
from sqlalchemy import select, update

from .tables.sqlcli import AsyncSessionLocal
from .tables.api_key import UserApiKey
from .tables.industrial_park import beijing_now
from utils.common.schema import GeneticResponse


def _alive(m):
    return (m.is_delete.is_(None)) | (m.is_delete.is_(False))


def _ser_api_key(k: UserApiKey) -> dict:
    return {"id": k.id, "name": k.name, "key_prefix": k.key_prefix,
            "created_by": k.created_by, "owner_name": k.owner_name,
            "status": 1 if (k.status if k.status is not None else 1) == 1 else 0,
            "last_used_time": k.last_used_time.strftime("%Y-%m-%d %H:%M:%S") if k.last_used_time else None,
            "create_time": k.create_time.strftime("%Y-%m-%d %H:%M:%S") if k.create_time else None}


async def create_api_key(user_id: int, owner_name: str, name: str,
                         key_hash: str, key_prefix: str):
    async with AsyncSessionLocal() as session:
        k = UserApiKey(name=name or "默认密钥", key_hash=key_hash, key_prefix=key_prefix,
                       created_by=user_id, owner_name=owner_name, status=1)
        session.add(k)
        await session.commit()
        await session.refresh(k)
        return GeneticResponse(data=_ser_api_key(k))


async def list_api_keys(user_id: int, is_admin_user: bool = False):
    """普通用户只见自己的 key；admin 可见全部（展示归属）。"""
    async with AsyncSessionLocal() as session:
        stmt = select(UserApiKey).where(_alive(UserApiKey))
        if not is_admin_user:
            stmt = stmt.where(UserApiKey.created_by == user_id)
        rows = (await session.scalars(stmt.order_by(UserApiKey.id.desc()))).all()
        return {"rows": [_ser_api_key(k) for k in rows], "total": len(rows)}


async def get_api_key_by_hash(key_hash: str):
    """鉴权用：命中启用中的 key 才返回（含刷新 last_used_time），否则 None。"""
    async with AsyncSessionLocal() as session:
        k = await session.scalar(select(UserApiKey).where(
            UserApiKey.key_hash == key_hash, _alive(UserApiKey), UserApiKey.status == 1))
        if not k:
            return None
        k.last_used_time = beijing_now()
        await session.commit()
        return {"id": k.id, "name": k.name, "created_by": k.created_by,
                "owner_name": k.owner_name}


async def get_api_key(key_id: int):
    async with AsyncSessionLocal() as session:
        k = await session.scalar(select(UserApiKey).filter_by(id=key_id))
        if not k or k.is_delete:
            return None
        return _ser_api_key(k)


async def set_api_key_status(key_id: int, status: int):
    async with AsyncSessionLocal() as session:
        await session.execute(update(UserApiKey).where(UserApiKey.id == key_id)
                               .values(status=status))
        await session.commit()
        return GeneticResponse()


async def soft_delete_api_key(key_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(update(UserApiKey).where(UserApiKey.id == key_id)
                               .values(is_delete=True))
        await session.commit()
        return GeneticResponse()
