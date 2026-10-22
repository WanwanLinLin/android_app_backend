from . import schema
from fastapi import APIRouter, status, Depends
from mybatisPlus.custom_plugin_orm import (get_custom_plugin_list, get_one_custom_plugin,
                                           create_custom_plugin, update_custom_plugin,
                                           delete_custom_plugin)
from utils.common.schema import GeneticResponse
from utils.admin_auth import current_admin, is_admin

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 个性插件：用户在基础插件之上定义的**私有**配置（自带完整 JSON 配置）。
# 所有登录用户均可创建；仅创建者本人可见可改可删可绑（严格私有，无平台归属）。
# admin 列表可见全部（用于治理/下架影响评估），但不代改别人的私有插件。
# 语义详见 mybatisPlus/custom_plugin_orm.py。

@router.get("/v1/customPlugin/list", summary="获取个性插件列表（按类别）", tags=["通用接口"])
async def _list_custom_plugins(category: str, admin: dict = Depends(current_admin)):
    """category: TTS | ASR | LLM。

    严格私有：普通用户仅见自己创建的；admin 见全部（仅治理用途）。
    所属基础插件已下架/已删除的个性插件对所有人不可见。
    """
    return GeneticResponse(data=await get_custom_plugin_list(
        category.upper(), is_admin(admin), admin["id"]))


@router.get("/v1/customPlugin/get/{id}", summary="获取一个个性插件", tags=["通用接口"])
async def _get_custom_plugin(id: int, admin: dict = Depends(current_admin)):
    data = await get_one_custom_plugin(id)
    if data: return GeneticResponse(data=data)
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/customPlugin/add", summary="创建个性插件", tags=["通用接口"])
async def _add_custom_plugin(info: schema.AddCustomPluginModel,
                             admin: dict = Depends(current_admin)):
    """config 为完整自带配置；type/tag 由后端按基础插件名强制写入，用户不可指定。
    个性插件严格私有，恒归创建者本人（platform_owned 已废弃并忽略）。"""
    payload = info.model_dump(exclude_none=True)
    payload.pop("platform_owned", None)  # 已废弃：不再有平台归属插件
    return await create_custom_plugin(is_admin(admin), admin["id"], **payload)


@router.post("/v1/customPlugin/update/{id}", summary="更新个性插件（仅创建者，仅 params）", tags=["通用接口"])
async def _update_custom_plugin(id: int, info: schema.UpdateCustomPluginModel,
                                admin: dict = Depends(current_admin)):
    """2026-10-22 起仅支持修改 config.params，其余字段（名称/描述/url/apikey/voice 等）锁定。"""
    return await update_custom_plugin(id, is_admin(admin), admin["id"], params=info.params)


@router.post("/v1/customPlugin/delete/{id}", summary="删除个性插件（仅创建者）", tags=["通用接口"])
async def _delete_custom_plugin(id: int, admin: dict = Depends(current_admin)):
    return await delete_custom_plugin(id, is_admin(admin), admin["id"])
