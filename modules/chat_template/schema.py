# -*- coding: utf-8 -*-
from typing import Dict
from pydantic import BaseModel, field_validator, ValidationError


class AddChatTemplateodel(BaseModel):
    module_path: str
    desc: str
