import time
import bcrypt
import asyncio
from . import schema
from fastapi import APIRouter, Depends, status
from utils.common.schema import GeneticResponse
from mybatisPlus.user_orm import get_password
from utils.randomString import create_numbering
from utils.auth import JwtAccessToken, validate_accesskey
from passlib.context import CryptContext
from setting import config_data

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.post("/v1/user/login")
async def _login(info: schema.UserLogin):    
    hashed_password = await get_password(info.username)
    if not hashed_password: return GeneticResponse(code=401, msg="Not authenticated")
    pres = info.password == hashed_password
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