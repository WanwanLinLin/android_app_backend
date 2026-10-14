from pydantic import BaseModel, model_validator
from typing import Union


class SaveDefaultSourceConfig(BaseModel):
    # 业务归属主体为租户；username 为终端旧字段别名，二者至少提供一个
    tenantname: Union[str, None] = None
    username: Union[str, None] = None
    llm_id: int
    tts_id: int
    asr_id: int

    @model_validator(mode="after")
    def _require_identity(self):
        if not (self.tenantname or self.username):
            raise ValueError("tenantname（或兼容字段 username）必须提供其一")
        return self
