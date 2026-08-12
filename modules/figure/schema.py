# -*- coding: utf-8 -*-
from pydantic import BaseModel, field_validator, ValidationError


class AddFigureModel(BaseModel):
    type: str
    name: str
    filename: str
    author: str
    version: str
    desc: str