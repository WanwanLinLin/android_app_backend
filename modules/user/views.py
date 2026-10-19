import bcrypt
from . import schema
from fastapi import APIRouter, Depends, status
from utils.common.schema import GeneticResponse
from mybatisPlus.user_orm import get_password, list_admins, get_admin
from mybatisPlus.tenant_orm import (create_tenant, list_tenants, get_tenant,
                                    update_tenant, delete_tenant, bind_source,
                                    unbind_source, list_bound_sources, set_source_default,
                                    list_tenants_by_username, is_tenant_owned)
from utils.auth import JwtAccessToken, validate_accesskey
from utils.common.auth import validate_stream_accesskey
from utils.admin_auth import current_admin, is_admin
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 身份与归属控制依赖（current_admin / is_admin）已下沉至 utils.admin_auth，
# 供资源池各模块（tts/asr/llm/chat_template）共用，避免循环导入。


async def ensure_tenant_access(admin: dict, tenant_id: int):
    """非 admin 角色只能操作自己名下的租户。无权时返回 403 响应体，有权返回 None。

    归属判定走 Tenant.user_id（无外键，应用层校验）。返回 403 而非 404：
    便于前端区分"不存在"和"不归你管"；若担心探测存在性可改为统一 404。
    """
    if is_admin(admin):
        return None
    if await is_tenant_owned(tenant_id, admin["id"]):
        return None
    return GeneticResponse(code=403, msg="无权操作该租户")


# ===================== 管理员账号（User 仅负责登录）=====================

@router.post("/v1/user/login")
async def _login(info: schema.UserLogin):
    """后台管理员登录，签发 JWT；租户管理接口需携带该 token。

    兼容两种口令提交方式，二者任一通过即放行：
      1. 提交固定盐 BCrypt 哈希（$2a$12$KpX5/PA4FXJkZNsnuYk41. 为盐），
         与 User.hashed_password == 比较。安卓端与 Web 管理后台（自
         2026-10-19 起，web/src/utils/password.js）均走此通路，
         明文不出网络。建号必须用同盐（scripts/create_user.py）。
      2. 提交明文密码，由 bcrypt.checkpw 与存储哈希比对（历史兼容
         通路，保留给未升级的旧终端）。
    """
    hashed_password = await get_password(info.username)
    if not hashed_password: return GeneticResponse(code=401, msg="Not authenticated")
    pres = info.password == hashed_password
    if not pres:
        try:
            pres = bcrypt.checkpw(info.password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            pres = False
    if not pres: return GeneticResponse(code=401, msg="Not authenticated")
    access_token = await JwtAccessToken(config_data["AUTH_CONFIG"]["secret_key"]).get_token(to_encode={"username": info.username})
    # role 一并返回，前端据此隐藏资源池的新增/编辑/删除入口（后端仍独立强校验）
    me = await get_admin(info.username)
    return GeneticResponse(data={
        "access_token": access_token,
        "token_type": "bearer",
        "role": (me or {}).get("role"),
        "nickname": (me or {}).get("nickname")
    })
    

# 登出接口
@router.post("/v1/user/logout")
async def logout(token: str = Depends(validate_accesskey)):
    return GeneticResponse(msg="Successfully logged out")


# ===================== 租户生命周期管理（User 的职责所在）=====================

@router.get("/v1/user/list", summary="管理员账号列表", tags=["租户管理"],
            dependencies=[Depends(validate_accesskey)])
async def _list_users():
    """供前端「所属管理员」下拉选择使用。"""
    data = await list_admins()
    return GeneticResponse(data=data)


@router.get("/v1/user/me", summary="当前登录账号信息", tags=["租户管理"])
async def _me(admin: dict = Depends(current_admin)):
    """前端登录后调用，获取自身 role，用于隐藏无权限的操作入口（如资源池编辑）。

    真正的权限校验仍以后端为准，这里只是展示层辅助。
    """
    return GeneticResponse(data=admin)


@router.post("/v1/tenant/add", summary="创建租户", tags=["租户管理"])
async def _add_tenant(info: schema.AddTenantModel, admin: dict = Depends(current_admin)):
    """创建租户，归属默认当前登录账号（Tenant.user_id = admin.id）。

    - 非 admin 角色：前端传的 user_id 一律忽略，强制归属自己；
    - admin 角色：可显式指定其他管理员（超管代建场景），不传也默认归自己。
    """
    payload = info.model_dump(exclude_none=True)
    if payload.get("user_id") is None or not is_admin(admin):
        payload["user_id"] = admin["id"]
    return await create_tenant(**payload)


@router.get("/v1/tenant/list", summary="租户列表", tags=["租户管理"])
async def _list_tenants(admin: dict = Depends(current_admin)):
    """admin 角色看全部租户；其余角色只看自己名下（Tenant.user_id 归属）。"""
    data = await list_tenants(user_id=None if is_admin(admin) else admin["id"])
    return GeneticResponse(data=data)


@router.get("/v1/tenant/get/{tenant_id}", summary="租户详情", tags=["租户管理"])
async def _get_tenant(tenant_id: int, admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    data = await get_tenant(tenant_id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="tenant not exist")


@router.post("/v1/tenant/update/{tenant_id}", summary="更新租户信息", tags=["租户管理"])
async def _update_tenant(tenant_id: int, info: schema.UpdateTenantModel,
                         admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    # 仅 admin 可改归属（user_id），防止非管理员把租户挪到自己/他人名下
    payload = info.model_dump(exclude_none=True)
    if not is_admin(admin):
        payload.pop("user_id", None)
    return await update_tenant(tenant_id, **payload)


@router.post("/v1/tenant/delete/{tenant_id}", summary="删除租户（软删除）", tags=["租户管理"])
async def _delete_tenant(tenant_id: int, admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    return await delete_tenant(tenant_id)


@router.get("/v1/user/tenants/{username}", summary="按管理员账号获取租户列表", tags=["租户管理"],
            dependencies=[Depends(validate_stream_accesskey)])
async def _list_tenants_by_username(username: str):
    """安卓端入口：用管理员账号名取该账号名下的租户列表（对称加密校验）。

    鉴权走 validate_stream_accesskey——请求头须带 dk=毫秒时间戳、
    token=SHA1(时间戳 + "\t" + app_key)，app_key 存于 Redis 的 hps_apikey。
    与 Web 后台的 JWT 接口相互独立，便于终端直接调用。

    归属关系走 Tenant.user_id 列（本项目不使用外键，引用完整性由应用层保证）。
    """
    data = await list_tenants_by_username(username)
    if data is None:
        return GeneticResponse(code=400, msg="user not exist")
    return GeneticResponse(data=data)


# ===================== 租户资源绑定（Tenant 添加 tts/asr/llm 等）=====================
# 以下四个接口均带 tenant_id，一律经 ensure_tenant_access 做归属校验：
# 非 admin 角色只能操作自己名下租户的资源，堵住越权改绑的洞。

@router.post("/v1/tenant/{tenant_id}/source/bind", summary="为租户绑定资源", tags=["租户管理"])
async def _bind_source(tenant_id: int, info: schema.BindSourceModel,
                       admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    return await bind_source(tenant_id, info.type, info.reference_id)


@router.post("/v1/tenant/{tenant_id}/source/unbind", summary="解绑租户资源", tags=["租户管理"])
async def _unbind_source(tenant_id: int, info: schema.BindSourceModel,
                         admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    return await unbind_source(tenant_id, info.type, info.reference_id)


@router.get("/v1/tenant/{tenant_id}/source/list", summary="租户已绑定资源列表", tags=["租户管理"])
async def _list_bound_sources(tenant_id: int, admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    return GeneticResponse(data=await list_bound_sources(tenant_id))


@router.post("/v1/tenant/{tenant_id}/source/setDefault", summary="设为租户默认资源", tags=["租户管理"])
async def _set_source_default(tenant_id: int, info: schema.BindSourceModel,
                              admin: dict = Depends(current_admin)):
    denied = await ensure_tenant_access(admin, tenant_id)
    if denied: return denied
    return await set_source_default(tenant_id, info.type, info.reference_id)
