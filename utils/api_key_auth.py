# -*- coding：utf-8 -*-
"""账号级 API Key 鉴权（模块无关，独立于后台 JWT 体系）。

调用方式：Authorization: Bearer sk-<40hex>（与 ragflow 的 Bearer 口径一致）。
安全口径：
  - 明文只在生成响应里返回一次，库里仅存 SHA256；
  - 校验命中后刷新 last_used_time（失败不影响鉴权结果）；
  - 失败统一抛 JwtAuthError（全局处理器返回 code=401），不区分
    "key 不存在/已停用"，避免给探测者反馈。
归属模型：key 归属某后台账号，消费模块（当前为知识库开放接口，后续
其它模块同样）以 key 归属者身份判定可见数据。管理接口见
/v1/user/apikey/*（modules/user/views.py）。
"""
import hashlib
import secrets

from fastapi import Header

from utils.apierror import JwtAuthError

KEY_PREFIX = "sk-"


def generate_key() -> tuple:
    """返回 (明文key, sha256哈希, 展示前缀)。"""
    plain = KEY_PREFIX + secrets.token_hex(20)
    return plain, hash_key(plain), plain[:11]


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


async def current_api_key(Authorization: str = Header(default=None)):
    """FastAPI 依赖：Bearer API Key → UserApiKey 记录（含归属用户）。

    返回 dict：id / name / created_by / owner_name（created_by 即权限主体）。
    各模块开放接口统一依赖本函数，勿再各自造 key 校验轮子。
    """
    if not Authorization or not Authorization.startswith("Bearer "):
        raise JwtAuthError()
    plain = Authorization[len("Bearer "):].strip()
    if not plain.startswith(KEY_PREFIX):
        raise JwtAuthError()
    from mybatisPlus import api_key_orm
    rec = await api_key_orm.get_api_key_by_hash(hash_key(plain))
    if not rec:
        raise JwtAuthError()
    return rec
