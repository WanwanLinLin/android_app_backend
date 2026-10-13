import redis
from setting import get_service

_redis = get_service("redis")

serect_pool = redis.ConnectionPool(host=_redis["host"], port=_redis["port"], password=_redis["pwd"], db=12, decode_responses=True)
