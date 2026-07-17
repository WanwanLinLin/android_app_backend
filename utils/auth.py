import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import timedelta, datetime
from jose import JWTError, jwt
from setting import config_data
from utils.apierror import JwtAuthError


class JwtAccessToken:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
    
    async def get_token(self, to_encode: Dict) -> str:
        expire = datetime.strftime(datetime.now() + timedelta(minutes=config_data["AUTH_CONFIG"]["access_token_expire_minutes"]), "%Y-%m-%d %H:%M:%S")
        to_encode["expire"] = expire
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm="HS256")
        return encoded_jwt
    
    async def verify_token(self, encoded_jwt: str):
        try:
            payload = jwt.decode(encoded_jwt, self.secret_key, algorithms=["HS256"])
            dist_time = datetime.strptime(datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
            src_time = datetime.strptime(payload["expire"], '%Y-%m-%d %H:%M:%S')
            time_diff = (dist_time - src_time).total_seconds()
            if time_diff > 0: raise JWTError()
            return {"code": 200, "msg": "ok", "data": payload}
            
        except JWTError as e:
            raise JwtAuthError()


async def validate_accesskey(Authorization = Header()):
    if Authorization.startswith("Bearer "): Authorization = Authorization.replace("Bearer ", "")
    return await JwtAccessToken(config_data["AUTH_CONFIG"]["secret_key"]).verify_token(Authorization)