# -*- coding: utf-8 -*-
from typing import Dict, Union
from pydantic import BaseModel


class AddCustomPluginModel(BaseModel):
    name: str
    base_plugin_id: int
    desc: Union[str, None] = None
    config: Dict
    # platform_owned 已废弃（个性插件严格私有，恒归创建者），保留字段仅为兼容旧前端传参
    platform_owned: Union[bool, None] = None


class UpdateCustomPluginModel(BaseModel):
    # 2026-10-22 起放开整个 config 编辑（url/apikey/voice/params 等均可修改），
    # 保存时后端按类别模板校验必含键（见 custom_plugin_orm.CONFIG_TEMPLATE）；
    # type/tag 仍由基础插件名强制覆盖，不允许用户改指向其它 provider 模块。
    config: Union[Dict, None] = None
