from pydantic import BaseModel
from typing import Union


class ConnectCheckModel(BaseModel):
    url: str
    port: Union[int, None] = None
    timeout: Union[int, None] = None
