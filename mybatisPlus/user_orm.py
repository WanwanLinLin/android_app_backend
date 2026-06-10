from datetime import datetime
from pydantic import BaseModel

from utils.common.schema import GeneticResponse
from .tables.industrial_park import Device2UserInfo
from .tables.sqlcli import AsyncSessionLocal


class UserModel(BaseModel):
    device_id: str
    username: str
    phone_number: str


if __name__ == "__main__":
    import asyncio
    