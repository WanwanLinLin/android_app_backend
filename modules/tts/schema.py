# -*- coding: utf-8 -*-
from pydantic import BaseModel, field_validator, ValidationError


class AddVoiceModel(BaseModel):
    type: str
    url: str
    desc: str
    tag: str
    voice: str
    apikey: str