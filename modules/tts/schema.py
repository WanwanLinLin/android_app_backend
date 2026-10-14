# -*- coding: utf-8 -*-
from typing import Union
from pydantic import BaseModel, field_validator, ValidationError


class AddVoiceModel(BaseModel):
    type: str
    url: str
    desc: str
    tag: str
    voice: str
    apikey: str


class UpdateVoiceModel(BaseModel):
    type: Union[str, None] = None
    url: Union[str, None] = None
    desc: Union[str, None] = None
    tag: Union[str, None] = None
    voice: Union[str, None] = None
    apikey: Union[str, None] = None
    additional_param: Union[dict, None] = None