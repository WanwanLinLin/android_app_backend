from typing import Any, Dict
from pydantic import BaseModel


class GeneticResponse(BaseModel):
    code: int = 200
    msg: str = "ok"
    data: Any = None