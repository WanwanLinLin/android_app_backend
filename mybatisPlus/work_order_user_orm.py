import json
from typing import List, Union
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from utils.common.schema import GeneticResponse
from .tables.work_order import Device2UserInfo, User
from .tables.sqlcli2 import WorkOrderAsyncSessionLocal
from datetime import datetime


async def wo_get_password(username: str):
    async with WorkOrderAsyncSessionLocal() as session:
        async with session.begin():
            user = await session.scalar(select(User).filter_by(username=username))
            if not user: return None
            return user.hashed_password
            