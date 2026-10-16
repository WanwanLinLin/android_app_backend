"""后台管理员身份与角色依赖（JWT → User 记录 → role）。

放在 utils 层供各模块共用：modules/user/views.py 依赖 tenant_orm 等，
若其他资源模块反向 import user.views 会形成循环导入，故下沉到本模块。

角色口径（与租户归属隔离一致，见 modules/user/views.py）：
  - role == "admin"：全量权限
  - 其余（如 "user"）：只能操作自己名下的租户，不可编辑资源池
"""
from fastapi import Depends, Header

from mybatisPlus.user_orm import get_admin
from utils.apierror import AdminRequiredError, JwtAuthError
from utils.auth import validate_accesskey


async def current_admin(Authorization: str = Header(default=None)):
    """JWT → username → 有效管理员记录（id/username/role/nickname）。

    validate_accesskey 只验签名有效性，不解析身份；本依赖补齐"你是谁"。
    账号被删（软删）后即便 token 未过期也一律拒绝。
    """
    resp = await validate_accesskey(Authorization)
    username = (resp or {}).get("data", {}).get("username")
    admin = await get_admin(username) if username else None
    if not admin:
        raise JwtAuthError()
    return admin


def is_admin(admin: dict) -> bool:
    return (admin.get("role") or "").lower() == "admin"


async def require_admin(admin: dict = Depends(current_admin)):
    """资源池写操作（新增/编辑/删除）专用依赖：仅 role=admin 放行。

    非管理员抛 AdminRequiredError → 全局异常处理器返回 code=403。
    """
    if not is_admin(admin):
        raise AdminRequiredError()
    return admin
