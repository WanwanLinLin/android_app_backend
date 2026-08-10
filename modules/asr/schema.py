# -*- coding: utf-8 -*-
from typing import Dict
from pydantic import BaseModel, field_validator, ValidationError


class AddLLModel(BaseModel):
    type: str
    url: str
    desc: str
    params: Dict
    apikey: str