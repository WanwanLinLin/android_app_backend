from pydantic import BaseModel
from typing import Union


class SessionQuery(BaseModel):
    tenant_id: Union[int, None] = None
    start: Union[str, None] = None
    end: Union[str, None] = None
    page: int = 1
    size: int = 20
