from . import schema
from fastapi import APIRouter, status, Depends
from mybatisPlus.base_plugin_orm import (get_base_plugin_list, get_one_base_plugin,
                                         add_one_base_plugin, update_one_base_plugin,
                                         delete_one_base_plugin, set_base_shelf_status,
                                         base_off_shelf_preview)
from mybatisPlus.tables.industrial_park import STATUS_ACTIVE, STATUS_OFF_SHELF
from utils.common.schema import GeneticResponse
from utils.admin_auth import require_admin, current_admin, is_admin
from utils.secret_mask import mask_secrets

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# 基础插件 = utils/providers/{tts,asr,llm} 下的代码插件登记表。
# 写操作（登记/修改/注销/上下架）一律仅 role=admin；普通用户只读且在
# 列表层面就看不到已下架项。语义详见 mybatisPlus/base_plugin_orm.py。

@router.post("/v1/basePlugin/list", summary="获取基础插件列表", tags=["通用接口"])
async def _list_base_plugins(admin: dict = Depends(current_admin)):
    """admin 看全量（含已下架，便于重新上架）；普通用户只看在售插件。

    列表会自动扫描插件目录，把磁盘上新增且未登记的文件登记为在售。
    """
    return GeneticResponse(data=mask_secrets(
        await get_base_plugin_list(only_active=not is_admin(admin))))


@router.post("/v1/basePlugin/add", summary="登记基础插件（需磁盘已有代码文件）", tags=["通用接口"])
async def _add_base_plugin(info: schema.AddBasePluginModel, admin: dict = Depends(require_admin)):
    return await add_one_base_plugin(**info.model_dump())


@router.get("/v1/basePlugin/get/{id}", summary="获取一个基础插件", tags=["通用接口"])
async def _get_base_plugin(id: int, admin: dict = Depends(current_admin)):
    data = await get_one_base_plugin(id)
    if data: return GeneticResponse(data=mask_secrets(data))
    return GeneticResponse(code=400, msg="data not exist")


@router.post("/v1/basePlugin/update/{id}", summary="更新基础插件元数据", tags=["通用接口"])
async def _update_base_plugin(id: int, info: schema.UpdateBasePluginModel,
                              admin: dict = Depends(require_admin)):
    return await update_one_base_plugin(id, **info.model_dump(exclude_none=True))


@router.post("/v1/basePlugin/delete/{id}", summary="注销基础插件（软删除）", tags=["通用接口"])
async def _delete_base_plugin(id: int, admin: dict = Depends(require_admin)):
    return await delete_one_base_plugin(id)


# ===================== 上下架（仅管理员）=====================
# 基础插件下架是「严格全面禁用」：个性插件连带隐藏、已绑定租户运行时直接拒绝，
# 影响面预览必须包含基于它的个性插件与租户绑定数。

@router.get("/v1/basePlugin/offShelfPreview/{id}", summary="下架影响面预览（个性插件+租户）",
            tags=["通用接口"])
async def _base_plugin_off_shelf_preview(id: int, admin: dict = Depends(require_admin)):
    return await base_off_shelf_preview(id)


@router.post("/v1/basePlugin/offShelf/{id}", summary="下架基础插件", tags=["通用接口"])
async def _base_plugin_off_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_base_shelf_status(id, STATUS_OFF_SHELF)


@router.post("/v1/basePlugin/onShelf/{id}", summary="上架基础插件", tags=["通用接口"])
async def _base_plugin_on_shelf(id: int, admin: dict = Depends(require_admin)):
    return await set_base_shelf_status(id, STATUS_ACTIVE)
