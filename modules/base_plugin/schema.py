# -*- coding: utf-8 -*-
from typing import Dict, Union
from pydantic import BaseModel


class AddBasePluginModel(BaseModel):
    category: str
    name: str
    desc: Union[str, None] = None
    default_config: Union[Dict, None] = None


class UpdateBasePluginModel(BaseModel):
    # 2026-10-22 起编辑面仅保留 desc：default_config 是登记时的参数模板，
    # 运行时参数（params）只在个性插件层编辑，基础插件不提供修改入口。
    desc: Union[str, None] = None
