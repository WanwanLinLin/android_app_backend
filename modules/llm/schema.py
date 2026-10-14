# -*- coding: utf-8 -*-
from typing import Dict, Union
from pydantic import BaseModel, field_validator, ValidationError


class AddLLModel(BaseModel):
    type: str
    url: str
    desc: str
    params: Dict
    apikey: str


class UpdateLLModel(BaseModel):
    type: Union[str, None] = None
    url: Union[str, None] = None
    desc: Union[str, None] = None
    params: Union[Dict, None] = None
    apikey: Union[str, None] = None