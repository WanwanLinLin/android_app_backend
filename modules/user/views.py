import bcrypt
from . import schema
from fastapi import APIRouter, Depends, status
from utils.common.schema import GeneticResponse
from mybatisPlus.user_orm import get_password, list_admins
from mybatisPlus.tenant_orm import (create_tenant, list_tenants, get_tenant,
                                    update_tenant, delete_tenant, bind_source,
                                    unbind_source, list_bound_sources, set_source_default,
                                    list_tenants_by_username)
from utils.auth import JwtAccessToken, validate_accesskey
from utils.common.auth import validate_stream_accesskey
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# ===================== 管理员账号（User 仅负责登录）=====================

@router.post("/v1/user/login")
async def _login(info: schema.UserLogin):
    """后台管理员登录，签发 JWT；租户管理接口需携带该 token。

    兼容两种口令提交方式，二者任一通过即放行：
      1. 直接提交与 User.hashed_password 一致的字符串（原有 == 比较，
         已在跑的终端按此方式工作，行为保持不变）；
      2. 提交明文密码，由 bcrypt.checkpw 与 bcrypt 哈希比对
         （Web 管理后台走此通路，否则明文永远无法登录）。
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
    return GeneticResponse(data={
        "access_token": access_token,
        "token_type": "bearer"
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


@router.post("/v1/tenant/add", summary="创建租户", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _add_tenant(info: schema.AddTenantModel):
    return await create_tenant(**info.model_dump(exclude_none=True))


@router.get("/v1/tenant/list", summary="租户列表", tags=["租户管理"],
            dependencies=[Depends(validate_accesskey)])
async def _list_tenants():
    return GeneticResponse(data=await list_tenants())


@router.get("/v1/tenant/get/{tenant_id}", summary="租户详情", tags=["租户管理"],
            dependencies=[Depends(validate_accesskey)])
async def _get_tenant(tenant_id: int):
    data = await get_tenant(tenant_id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="tenant not exist")


@router.post("/v1/tenant/update/{tenant_id}", summary="更新租户信息", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _update_tenant(tenant_id: int, info: schema.UpdateTenantModel):
    return await update_tenant(tenant_id, **info.model_dump(exclude_none=True))


@router.post("/v1/tenant/delete/{tenant_id}", summary="删除租户（软删除）", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _delete_tenant(tenant_id: int):
    return await delete_tenant(tenant_id)


@router.get("/v1/user/tenants/{username}", summary="按管理员账号获取租户列表", tags=["租户管理"],
            dependencies=[Depends(validate_stream_accesskey)])
async def _list_tenants_by_username(username: str):
    """安卓端入口：用管理员账号名取该账号名下的租户列表（对称加密校验）。

    鉴权走 validate_stream_accesskey——请求头须带 dk=毫秒时间戳、
    token=SHA1(时间戳 + "\t" + app_key)，app_key 存于 Redis 的 hps_apikey。
    与 Web 后台的 JWT 接口相互独立，便于终端直接调用。

    归属关系走 Tenant.user_id 外键（FK -> User.id）。
    """
    data = await list_tenants_by_username(username)
    if data is None:
        return GeneticResponse(code=400, msg="user not exist")
    return GeneticResponse(data=data)


# ===================== 租户资源绑定（Tenant 添加 tts/asr/llm 等）=====================

@router.post("/v1/tenant/{tenant_id}/source/bind", summary="为租户绑定资源", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _bind_source(tenant_id: int, info: schema.BindSourceModel):
    return await bind_source(tenant_id, info.type, info.reference_id)


@router.post("/v1/tenant/{tenant_id}/source/unbind", summary="解绑租户资源", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _unbind_source(tenant_id: int, info: schema.BindSourceModel):
    return await unbind_source(tenant_id, info.type, info.reference_id)


@router.get("/v1/tenant/{tenant_id}/source/list", summary="租户已绑定资源列表", tags=["租户管理"],
            dependencies=[Depends(validate_accesskey)])
async def _list_bound_sources(tenant_id: int):
    return GeneticResponse(data=await list_bound_sources(tenant_id))


@router.post("/v1/tenant/{tenant_id}/source/setDefault", summary="设为租户默认资源", tags=["租户管理"],
             dependencies=[Depends(validate_accesskey)])
async def _set_source_default(tenant_id: int, info: schema.BindSourceModel):
    return await set_source_default(tenant_id, info.type, info.reference_id)
