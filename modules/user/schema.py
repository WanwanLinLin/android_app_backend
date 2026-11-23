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


class AddApiKeyModel(BaseModel):
    """生成账号级 API Key（模块无关，供各模块开放接口共用）。"""
    name: Union[str, None] = None  # 备注名，可空
