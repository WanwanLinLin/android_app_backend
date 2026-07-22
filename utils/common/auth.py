import time
import redis
import hashlib
from .redis_cli import serect_pool
from fastapi import Header, Query
from utils.apierror import AccessKeyAuthError


class OnewayEncryption:
    
    def __init__(self):
        pass

    def get_sha1(self, string: str):
        if string is None or len(string) == 0:
            return None

        sha1 = hashlib.sha1()
        sha1.update(string.encode('utf-8'))
        return sha1.hexdigest()
    
    def build_token(self, time_stamp, app_key):
        text = f"{time_stamp}\t{app_key}"
        token = self.get_sha1(text)
        return token
    
    def verify_token(self, time_stamp, token):
        if (int(time.time() * 1000) - int(time_stamp)) > 50000: return 0
        r = redis.Redis(connection_pool=serect_pool)
        list_length = r.llen("hps_apikey")
        for index in range(list_length):
            apikey = r.lindex("hps_apikey", index)
            if self.build_token(time_stamp, apikey) == token: return 1
        return 0


async def validate_stream_accesskey(dk = Header(default=None), token = Header(default=None), key_hopesen: str = Query(default=None)):
    # double auth
    # if key_hopesen and key_hopesen in key_hopesen_codebook: return
    if not dk or not token: raise AccessKeyAuthError
    if not OnewayEncryption().verify_token(dk, token): raise AccessKeyAuthError
    return


# 示例用法
if __name__ == "__main__":
    time_stamp = int(time.time())  # 示例时间戳
    app_key = "hps_vgH7n7UCKjVr7k8kmdM"
    token = OnewayEncryption().build_token(time_stamp, app_key)
    print(token)