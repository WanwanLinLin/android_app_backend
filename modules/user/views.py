import bcrypt
from . import schema
from fastapi import APIRouter, Depends, status
from utils.common.schema import GeneticResponse
from mybatisPlus.user_orm import get_password
from mybatisPlus.tenant_orm import (create_tenant, list_tenants, get_tenant,
                                    update_tenant, delete_tenant)
from utils.auth import JwtAccessToken, validate_accesskey
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# ===================== 管理员账号（User 仅负责登录）=====================

@router.post("/v1/user/login")
async def _login(info: schema.UserLogin):
    """后台管理员登录，签发 JWT；租户管理接口需携带该 token。"""
    hashed_password = await get_password(info.username)
    if not hashed_password: return GeneticResponse(code=401, msg="Not authenticated")
    pres = info.password == hashed_password
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
