import time
import asyncio
from . import schema
from fastapi import APIRouter, Depends, status
from utils.common.schema import GeneticResponse
from mybatisPlus.task_orm import create_task
from mybatisPlus.engineer_orm import list_engineers_detail
from mybatisPlus.user_orm import get_password
from utils.randomString import create_numbering
from utils.auth import JwtAccessToken, validate_accesskey
from passlib.context import CryptContext
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.get("/v1/user/engineer/list")
async def _list_engineers():
    return GeneticResponse(data=await list_engineers_detail())


@router.post("/v1/user/login")
async def _login(info: schema.UserLogin):
    hashed_password = await get_password(info.username)
    if not hashed_password: return GeneticResponse(code=401, msg="Not authenticated")
    start_time = time.perf_counter()
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pres = await asyncio.to_thread(pwd_context.verify, info.password, hashed_password)
    if not pres: return GeneticResponse(code=401, msg="Not authenticated")
    access_token = await JwtAccessToken(config_data["AUTH_CONFIG"]["secret_key"]).get_token(to_encode={"username": info.username})
    return GeneticResponse(data={
        "access_token": access_token,
        "token_type": "bearer"
    })
    

# 登出接口
@router.post("/v1/user/logout")
async def logout(token: str = Depends(validate_accesskey)):
    return GeneticResponse(msg="Successfully logged out")