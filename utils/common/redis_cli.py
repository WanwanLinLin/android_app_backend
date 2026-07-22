import redis
from setting import config_data

serect_pool = redis.ConnectionPool(host=config_data["SERVICES"][-3]["host"], port=config_data["SERVICES"][-3]["port"], password=config_data["SERVICES"][-3]["pwd"], db=12, decode_responses=True)

monitor_task_pool = redis.ConnectionPool(host=config_data["SERVICES"][-3]["host"], port=config_data["SERVICES"][-3]["port"], password=config_data["SERVICES"][-3]["pwd"], db=14, decode_responses=True)