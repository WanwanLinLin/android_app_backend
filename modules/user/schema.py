from pydantic import BaseModel
from typing import Union


class UserLogin(BaseModel):
    username: str
    password: str


class AddTenantModel(BaseModel):
    tenantname: str
    nickname: Union[str, None] = None
    job: Union[str, None] = None
    phone_number: Union[str, None] = None


class UpdateTenantModel(BaseModel):
    nickname: Union[str, None] = None
    job: Union[str, None] = None
    phone_number: Union[str, None] = None
