# publisher.py 发布者
import asyncio
import json
from aiomqtt import Client
from setting import config_data


class AsyncMqtt:
    
    def __init__(self):
        self.hostname = config_data["SERVICES"][-1]["host"]
        self.port = config_data["SERVICES"][-1]["port"]
        self.username = config_data["SERVICES"][-1]["username"]
        self.password = config_data["SERVICES"][-1]["password"]

    async def publish_message(self, topic: str, msg: str, qos: int = 0, retain: bool = False):
        # 连接 → 发布 → 自动断开
        async with Client(hostname=self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    keepalive=60) as client:
            # 核心：发布消息
            await client.publish(
                topic=topic,      # 主题
                payload=msg,  # 消息内容
                qos=qos,                  # QoS 等级
                retain=retain,                  # 是否持久化
            )
        return 1


# ============== 启动 ==============
if __name__ == "__main__":
    # 运行
    print(1)