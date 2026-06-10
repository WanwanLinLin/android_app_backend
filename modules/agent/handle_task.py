# -*- coding：utf-8 -*-
import time
import json
import redis
import asyncio
from openai import AsyncOpenAI
from datetime import datetime, timedelta
from mybatisPlus.device_orm import get_device_detail_by_device_id, get_device_detail_by_engineer_id
from mybatisPlus.task_orm import get_engineer_by_id, update_task, get_task_info_by_id, confirm_task
from mybatisPlus.engineer_orm import list_all_engineer
from setting import config_data
from utils.tools import extract_json_from_response
from utils.async_mqtt_client import AsyncMqtt
from utils.getLogs import LOG
from utils.common.redis_cli import monitor_task_pool


async def receive_task_agent(topic: str, task_id: str, event_description: str, location: str,
                             device_id: str):
    """
    device_id: str 提出问题的人的设备id
    """
    r = redis.Redis(connection_pool=monitor_task_pool)
    engineers = (await list_all_engineer()).data
    report_engineer_id = (await get_device_detail_by_device_id(device_id=device_id)).id
    sys_prompt = f"""
现在是北京时间：{datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')},
根据用户提出的问题，从工程师列表中挑选出最适合解决该问题工程师列表，并给出解决方案。返回以下格式的 JSON：

{{
  "ids": "工程师id列表",
  "names": "工程师名称列表",
  "solution": "解决方案",
  "start_time": "预计开始解决的时间。"
}}
注意：
- 解决方案中必须包含事故可能的原因、工程师名字、目标地点以及开始解决时间，注意要用第三人称
- 如果用户意图不明确导致无法找到合适的解决方案，那么所有的字段都返回null
"""
    user_prompt = f"用户提出的问题：{event_description}；工程师列表：{engineers}"
    llm_client = AsyncOpenAI(
        base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
        api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
        timeout=60,
        max_retries=3
    )
    completion = await llm_client.chat.completions.create(
        model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": True}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    LOG(f"LLM: _json_str is {_json_str}", "DEBUG")
    json_str = json.loads(_json_str, strict=False)
    person_report_topic = f"task/{device_id}"
    if "ids" in json_str and json_str["ids"] and json_str["ids"] != "null":
        person_report_topic_msg = {
            "type": "common",
            "text": "已经成功创建工单并指派工程师解决问题。",
            "success": True
        }
        engineer_msg = {
            "type": "receive_task",
            "text": json_str["solution"],
            "task_id": task_id,
            "status": "pending"
        }
        engineer_device_id = (await get_device_detail_by_engineer_id(json_str["ids"][0])).device_id
        engineer_topic = f"task/{engineer_device_id}"
        # 发给上报问题者
        if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
            LOG(f"✅ 任务 {task_id} 成功向问题提出者 {person_report_topic} 推送已经确认任务消息：{json_str}", "DEBUG")
        # 发给解决方案给对应的工程师
        if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
            LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送解决方案：{json_str}，正在等待工程师确认", "DEBUG")
        await update_task(task_id, 0, solution=_json_str, engineer_id=json_str["ids"][0], report_engineer_id=report_engineer_id)
        r.setex(task_id, 60 * 60, "valid")
        asyncio.create_task(monitor_task_agent(task_id, json_str["solution"], engineer_device_id, device_id))
    else:
        json_str["success"] = False
        json_str["type"] = "create_task"
        json_str["status"] = "error"
        person_report_topic_msg = {
            "type": "common",
            "text": "很抱歉，无法找到合适的工程师处理问题，请你再次详细描述你的问题和需求，我会给你新的解决方案。",
            "success": False
        }
        await update_task(task_id, mode=-1, solution=json.dumps(json_str, ensure_ascii=False), report_engineer_id=report_engineer_id)
        if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
            LOG(f"❌ 任务 {task_id} 无法向 {person_report_topic} 推送合适的解决方案.", "DEBUG")


# 由工程师确认任务是否被接受
async def monitor_task_agent(task_id: str, solution: str, engineer_device_id: str, report_device_id: str):
    LOG(f"✅ 任务 {task_id} 开始在后台调度运行...", "DEBUG")
    await asyncio.sleep(30)
    start_time = time.perf_counter()
    r = redis.Redis(connection_pool=monitor_task_pool)
    task_info = await get_task_info_by_id(task_id)
    if not task_info:
        LOG(f"❌ 任务 {task_id} 不存在！.", "DEBUG")
        return
    while r.get(task_id):
        task_info = await get_task_info_by_id(task_id)
        update_diff = abs(datetime.now() - datetime.strptime(task_info.update_time, "%Y-%m-%d %H:%M:%S")).total_seconds()
        if update_diff < 30:
            await asyncio.sleep(update_diff)
            continue
        elif task_info.status == 0:    
            engineer_msg = {
                "type": "receive_task",
                "text": solution,
                "task_id": task_id,
                "status": "pending",
                "device_id": engineer_device_id
            }
            engineer_topic = f"task/{engineer_device_id}"
            # 发给解决方案给对应的工程师
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 重新推送解决方案消息：{engineer_msg}，正在等待工程师确认", "DEBUG")
            await asyncio.sleep(30)
        elif task_info.status == 1:
            engineer_msg = {
                "type": "start_task",
                "text": "请问你是否已经到达现场并开始工作？",
                "task_id": task_id,
                "status": "pending",
                "device_id": engineer_device_id
            }
            engineer_topic = f"task/{engineer_device_id}"
            # 询问师傅是否到达现场并开始工作?
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送消息：{engineer_msg}，正在等待工程师确认", "DEBUG")
            await asyncio.sleep(30)
        elif task_info.status == 2:
            engineer_msg = {
                "type": "finish_task",
                "text": "请问你是否已经完成工作？",
                "task_id": task_id,
                "status": "pending",
                "device_id": engineer_device_id
            }
            engineer_topic = f"task/{engineer_device_id}"
            # 询问师傅是否到达现场并开始工作?
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送消息：{engineer_msg}，正在等待工程师确认", "DEBUG")
            await asyncio.sleep(30)
        elif task_info.status == 3:
            push_msg = {
                        "type": "common",
                        "text": "故障已经处理完成！",
                        "status": "finish",
                        "task_id": task_id
                    }
            if await AsyncMqtt().publish_message(f"task/{report_device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 task/{report_device_id} 推送消息：{push_msg}", "DEBUG")
            return
    
    push_msg = {
                "type": "common",
                "text": "很抱歉，任务执行失败了！",
                "status": "finish",
                "task_id": task_id
            }
    if await AsyncMqtt().publish_message(f"task/{report_device_id}", json.dumps(push_msg, ensure_ascii=False)):
        LOG(f"✅ 任务 {task_id} 成功向 task/{report_device_id} 推送消息：{push_msg}", "DEBUG")
    await update_task(task_id, mode=2, status=-1)
    return


class MonitorTaskWorkflow:
    def __init__(self, task_id: str, device_id: str):
        self.task_id = task_id
        self.device_id = device_id
    
    async def receive_task(self, confirm_msg: str):
        sys_prompt = f"""
判断用户的意图是同意还是拒绝。返回以下格式的 JSON：

{{
"intention": "accept/reject"
}}
"""
        user_prompt = confirm_msg
        llm_client = AsyncOpenAI(
            base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
            api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
            timeout=60,
            max_retries=3
        )
        completion = await llm_client.chat.completions.create(
            model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        response = completion.choices[0].message.content
        _json_str = extract_json_from_response(response)
        LOG(f"LLM: _json_str is {_json_str}", "DEBUG")
        json_str = json.loads(_json_str, strict=False)
        if json_str["intention"] == "accept":
            await update_task(self.task_id, mode=2, status=1)
            push_msg = {
                        "type": "common",
                        "ack": True,
                        "msg": "好的，已经为你创建工单任务，请尽快赶往现场。",
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=1)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")
        else:
            push_msg = {
                "type": "common",
                "msg": "未收到确认信息，系统将在30秒后发起重新确认请求。",
                "status": "retry",
                "task_id": self.task_id
            }
            await update_task(self.task_id, mode=3)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")
    
    async def start_task(self, confirm_msg: str):
        sys_prompt = f"""
判断用户是否已经开始工作？。返回以下格式的 JSON：

{{
"start_work": "true/false"
}}
"""
        user_prompt = confirm_msg
        llm_client = AsyncOpenAI(
            base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
            api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
            timeout=60,
            max_retries=3
        )
        completion = await llm_client.chat.completions.create(
            model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        response = completion.choices[0].message.content
        _json_str = extract_json_from_response(response)
        LOG(f"LLM: _json_str is {_json_str}", "DEBUG")
        json_str = json.loads(_json_str, strict=False)
        if json_str["start_work"] == "true" or json_str["start_work"] is True:
            await update_task(self.task_id, mode=2, status=1)
            push_msg = {
                        "type": "common",
                        "ack": True,
                        "msg": "好的，系统将在30秒后查询最新进度。",
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=2)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")     
        else:
            push_msg = {
                "type": "common",
                "msg": "工程师还未开始任务，系统将在30秒后发起重新查询进度。",
                "status": "retry",
                "task_id": self.task_id
            }
            await update_task(self.task_id, mode=3)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")   
        
    async def finish_task(self, confirm_msg: str):
        sys_prompt = f"""
判断用户是否已经完成工作？。返回以下格式的 JSON：

{{
"finish_work": "true/false"
}}
"""
        user_prompt = confirm_msg
        llm_client = AsyncOpenAI(
            base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
            api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
            timeout=60,
            max_retries=3
        )
        completion = await llm_client.chat.completions.create(
            model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        response = completion.choices[0].message.content
        _json_str = extract_json_from_response(response)
        LOG(f"LLM: _json_str is {_json_str}", "DEBUG")
        json_str = json.loads(_json_str, strict=False)
        if json_str["finish_work"] == "true" or json_str["finish_work"] is True:
            await update_task(self.task_id, mode=2, status=3)
            push_msg = {
                        "type": "common",
                        "ack": True,
                        "msg": "好的，已经更新系统工单状态，您辛苦了！",
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=3)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")    
        else:
            push_msg = {
                "type": "common",
                "msg": "任务还未完成，系统将在30秒后发起重新查询进度。",
                "status": "retry",
                "task_id": self.task_id
            }
            await update_task(self.task_id, mode=3)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")   
        
            