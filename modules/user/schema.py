from pydantic import BaseModel
from typing import Union


class UserLogin(BaseModel):
    username: str
    password: str


class AddTenantModel(BaseModel):
    tenantname: str
    user_id: Union[int, None] = None
    nickname: Union[str, None] = None
    job: Union[str, None] = None
    phone_number: Union[str, None] = None


class UpdateTenantModel(BaseModel):
    user_id: Union[int, None] = None
    nickname: Union[str, None] = None
    job: Union[str, None] = None
    phone_number: Union[str, None] = None


class BindSourceModel(BaseModel):
    """租户绑定资源。type 取 TTS | ASR | LLM | FIGURE | CHATTEMPLATE。"""
    type: str
    reference_id: int
