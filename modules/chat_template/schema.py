# -*- coding: utf-8 -*-
from typing import Dict, Union
from pydantic import BaseModel, field_validator, ValidationError


class AddChatTemplateodel(BaseModel):
    module_path: str
    desc: str


class UpdateChatTemplateModel(BaseModel):
    module_path: Union[str, None] = None
    desc: Union[str, None] = None
