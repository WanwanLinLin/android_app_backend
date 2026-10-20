# -*- coding: utf-8 -*-
from typing import Dict, Union
from pydantic import BaseModel, field_validator, ValidationError


class AddChatTemplateodel(BaseModel):
    module_path: str
    desc: str
    content: Union[str, None] = None


class UpdateChatTemplateModel(BaseModel):
    module_path: Union[str, None] = None
    desc: Union[str, None] = None
    content: Union[str, None] = None
