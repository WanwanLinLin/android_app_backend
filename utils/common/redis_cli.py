import redis
from setting import config_data

monitor_task_pool = redis.ConnectionPool(host=config_data["SERVICES"][-3]["host"], port=config_data["SERVICES"][-3]["port"], password=config_data["SERVICES"][-3]["pwd"], db=14, decode_responses=True)