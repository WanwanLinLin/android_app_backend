import time
import json
import asyncio
from aiomqtt import MqttError, Client
import requests
import threading
from queue import Queue
# import paho.mqtt.client as mqtt
from modules.agent.handle_task import MonitorTaskWorkflow
from setting import config_data
from utils.getLogs import LOG
# from paho.mqtt.enums import CallbackAPIVersion


# ===================== 配置项（请根据你的环境修改）=====================
MQTT_BROKER = config_data["SERVICES"][-1]["host"]  # MQTT服务器地址
MQTT_PORT = config_data["SERVICES"][-1]["port"]           # 默认端口（无SSL）
SUB_TOPIC = config_data["SERVICES"][-1]["server_task_receive_topic"]    # 测试主题
MQTT_USER = config_data["SERVICES"][-1]["username"]        # 有鉴权就填用户名
MQTT_PASSWORD = config_data["SERVICES"][-1]["password"]        # 有鉴权就填密码
# =============================================================

# 全局客户端（方便全函数使用）
client = None
task_queue = Queue(maxsize=200)


async def wait_for_task_msg():
    while 1:
        if not task_queue.empty():
            task_msg = task_queue.get()
            LOG(f"\n📩 获取到任务：{task_msg} 开始执行...", "DEBUG")
            try:
                if task_msg["type"] == "confirm_task_position":
                    await MonitorTaskWorkflow(task_msg["task_id"], task_msg["device_id"]).confirm_task_position(task_msg["text"])
                elif task_msg["type"] == "receive_task":
                    await MonitorTaskWorkflow(task_msg["task_id"], task_msg["device_id"]).receive_task(task_msg["text"])
                elif task_msg["type"] == "start_task":
                    await MonitorTaskWorkflow(task_msg["task_id"], task_msg["device_id"]).start_task(task_msg["text"])
                elif task_msg["type"] == "finish_task":
                    await MonitorTaskWorkflow(task_msg["task_id"], task_msg["device_id"]).finish_task(task_msg["text"])
                elif task_msg["type"] == "start_multi_task":
                    ...
                elif task_msg["type"] == "finish_multi_task":
                    ...
                else:
                    # 进入意图识别阶段
                    await MonitorTaskWorkflow(task_msg["task_id"], task_msg["device_id"]).intention_classification(task_msg["text"], task_msg["location"])
            except Exception as e:
                LOG(f"❌ 任务 {task_msg} 处理失败：{str(e)}", "DEBUG")
        else:
            await asyncio.sleep(0.1)


# ============== 异步消息处理（替代原来的 on_message） ==============
async def handle_messages(client: Client):
    """异步监听并处理 MQTT 消息"""
    await client.subscribe(SUB_TOPIC)
    LOG(f"📥 正在监听主题：{SUB_TOPIC}", "DEBUG")
    async for msg in client.messages:
        topic = msg.topic
        content = msg.payload.decode('utf-8')
        LOG(f"\n📩 收到消息 | 主题：{topic}", "DEBUG")
        LOG(f"内容：{content}", "DEBUG")

        try:
            data = json.loads(content, strict=False)
            task_queue.put(data)  # 异步队列 put
        except Exception as e:
            LOG(f"error message：{content}", "DEBUG")


# ============== 异步 MQTT 主任务 ==============
async def mqtt_async():
    """异步 MQTT 客户端主函数"""
    while True:
        try:
            # 创建异步 MQTT 客户端
            async with Client(
                hostname=MQTT_BROKER,
                port=MQTT_PORT,
                username=MQTT_USER,
                password=MQTT_PASSWORD,
                keepalive=60
            ) as client:

                LOG("✅ MQTT 连接成功！", "DEBUG")
                
                # 启动消息处理协程
                await handle_messages(client)

        except MqttError as e:
            LOG(f"❌ MQTT 连接断开/失败：{str(e)}，3秒后重连...", "DEBUG")
            await asyncio.sleep(3)  # 异步等待重连


async def main():
    # 3. 并发执行，等待所有完成
    await asyncio.gather(mqtt_async(), wait_for_task_msg())

# ============== 启动 ==============
if __name__ == "__main__":
    # mqtt_init()
    asyncio.run(main())