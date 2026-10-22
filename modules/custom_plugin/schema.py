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
    # 2026-10-22 起编辑仅开放 params：名称/描述/基础插件/url/apikey/voice 等
    # 全部锁定（url 等由基础插件 default_config 决定，改它们会让基础插件失去意义）
    params: Union[Dict, None] = None
