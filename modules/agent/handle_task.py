# -*- coding：utf-8 -*-
import time
import json
import redis
import asyncio
from openai import AsyncOpenAI
from datetime import datetime, timedelta
from mybatisPlus.device_orm import get_device_detail_by_device_id, get_device_detail_by_engineer_id
from mybatisPlus.task_orm import update_task, get_task_info_by_id, confirm_task
from mybatisPlus.engineer_orm import get_engineer_by_id, list_all_engineer
from mybatisPlus.work_order_task_orm import wo_update_save_one_task, wo_update_task_status
from setting import config_data
from utils.tools import extract_json_from_response
from utils.async_mqtt_client import AsyncMqtt
from utils.getLogs import LOG
from utils.common.redis_cli import monitor_task_pool
from utils.common.enumTaskType import TaskTypeEnum
from .make_solution import get_perfect_solution
from .intention_classify import get_user_intention, is_legal_position
from geopy.distance import geodesic


async def receive_task_agent(topic: str, task_id: str, event_description: str, location: str,
                             device_id: str):
    """
    device_id: str 提出问题的人的设备id
    """
    r = redis.Redis(connection_pool=monitor_task_pool)
    engineers = (await list_all_engineer()).data
    report_engineer_id = (await get_device_detail_by_device_id(device_id=device_id)).id
    person_report_topic = f"task/{device_id}"
    # 先判断用户的问题是否合规？
    intention = await get_user_intention(event_description)
    if intention["type"] == TaskTypeEnum.Undefied.value:
        person_report_topic_msg = {
                    "type": "common",
                    "text": f"很抱歉，当前只支持{TaskTypeEnum.SanitationTreatment.value}、{TaskTypeEnum.FaultReporting.value}、{TaskTypeEnum.SecurityIncident.value}",
                    "success": False
                }
        await update_task(task_id, mode=-1, solution=json.dumps([], ensure_ascii=False), report_engineer_id=report_engineer_id)
        await update_task(task_id, mode=2, status=-1)
        await wo_update_task_status(task_id, -1)
        if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
            LOG(f"❌ 任务 {task_id} 无法向 {person_report_topic} 推送合适的解决方案.", "DEBUG")
    else:
        if intention["position"] == TaskTypeEnum.Undefied.value:
            # 需要用户说出详细地点？
            asyncio.create_task(waiting_for_legal_position_and_picture(task_id, report_engineer_id, device_id, event_description, intention["type"]))
            return
        else:
            r.setex(f"{task_id}_confirm_task_position", 60 * 60, intention["position"])
            asyncio.create_task(waiting_for_legal_position_and_picture(task_id, report_engineer_id, device_id, event_description, intention["type"]))
            return
        # else:
        #     json_str = await get_perfect_solution(event_description, (await get_device_detail_by_device_id(device_id=device_id)).location)
        #     person_report_topic = f"task/{device_id}"
        #     if "ids" in json_str and json_str["ids"] and json_str["ids"] != "null":
        #         person_report_topic_msg = {
        #             "type": "common",
        #             "text": "已经成功创建工单并指派工程师解决问题。",
        #             "success": True
        #         }
        #         engineer_msg = {
        #             "type": "receive_task",
        #             "text": json_str["solution"],
        #             "task_id": task_id,
        #             "status": "pending"
        #         }
        #         engineer_device_id = (await get_device_detail_by_engineer_id(json_str["ids"][0])).device_id
        #         engineer_topic = f"task/{engineer_device_id}"
        #         # 发给上报问题者
        #         if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
        #             LOG(f"✅ 任务 {task_id} 成功向问题提出者 {person_report_topic} 推送已经确认任务消息：{json_str}", "DEBUG")
        #         # 发给解决方案给对应的工程师
        #         if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
        #             LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送解决方案：{json_str}，正在等待工程师确认", "DEBUG")
        #         await update_task(task_id, 0, solution=json_str, engineer_id=json_str["ids"][0], report_engineer_id=report_engineer_id)
        #         r.setex(task_id, 60 * 60, "valid")
        #         # 保存解决方案到工单数据库
        #         await wo_save_one_task(task_id=task_id, title=json_str["title"], description=json_str["solution"],
        #                                owner_id=json_str["ids"][0], task_type=intention["type"])
        #         asyncio.create_task(monitor_task_agent(task_id, json_str["solution"], engineer_device_id, device_id))
        #     else:
        #         json_str["success"] = False
        #         json_str["type"] = "create_task"
        #         json_str["status"] = "error"
        #         person_report_topic_msg = {
        #             "type": "common",
        #             "text": "很抱歉，无法找到合适的工程师处理问题，请你再次详细描述你的问题和地点，我会尝试给你输出的解决方案。",
        #             "success": False
        #         }
        #         await update_task(task_id, mode=-1, solution=json.dumps(json_str, ensure_ascii=False), report_engineer_id=report_engineer_id)
        #         if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
        #             LOG(f"❌ 任务 {task_id} 无法向 {person_report_topic} 推送合适的解决方案.", "DEBUG")


# 等待用户提供合规的地点后再创建任务
async def waiting_for_legal_position_and_picture(task_id: str, report_engineer_id: str, report_device_id: str, event_description: str,
                                     task_type: str):
    await asyncio.sleep(2)
    r = redis.Redis(connection_pool=monitor_task_pool)
    while 1:
        if r.get(f"{task_id}_confirm_task_position"): break
        else:
            reporter_msg = {
                "type": "confirm_task_position",
                "text": "我还需要确认具体位置，请补充楼栋、楼层或附近点位。",
                "task_id": task_id,
                "status": "pending",
                "device_id": report_device_id
            }
            engineer_topic = f"task/{report_device_id}"
            # 发给解决方案给对应的工程师
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(reporter_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送消息：{reporter_msg}", "DEBUG")
            await asyncio.sleep(15)
    position = r.get(f"{task_id}_confirm_task_position")
    if position: event_description += f" 具体位置：{position}"
    # 等待reporter上传照片
    while 1:
        task_info = await get_task_info_by_id(task_id)
        if not task_info.photo_path:
            reporter_msg = {
                "type": "upload_start_task_image",
                "text": "收到，已识别到您反馈的问题。我需要一张现场照片来判断情况，请在 App 中上传。",
                "task_id": task_id,
                "status": "pending",
                "device_id": report_device_id
            }
            engineer_topic = f"task/{report_device_id}"
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(reporter_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向reporter {engineer_topic} 推送消息：{reporter_msg}", "DEBUG")
            await asyncio.sleep(15)
        else: break
    
    json_str = await get_perfect_solution(event_description, (await get_device_detail_by_device_id(device_id=report_device_id)).location)
    person_report_topic = f"task/{report_device_id}"
    if "ids" in json_str and json_str["ids"] and json_str["ids"] != "null":
        person_report_topic_msg = {
            "type": "common",
            "text": "照片已收到。我正在结合现场位置和处理规范判断处理方式，并为您匹配合适人员。",
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
        await update_task(task_id, 0, solution=json.dumps(json_str, ensure_ascii=False), engineer_id=json_str["ids"][0], report_engineer_id=report_engineer_id)
        r.setex(task_id, 60 * 60, "valid")
        # 保存解决方案到工单数据库
        await wo_update_save_one_task(task_id=task_id, title=json_str["title"], description=json_str["solution"],
                                owner_id=json_str["ids"][0], task_type=task_type, assignee_ids=json.dumps(json_str["ids"]))
        asyncio.create_task(monitor_task_agent(task_id, json_str["solution"], engineer_device_id, report_device_id, json_str["title"], position))
    else:
        json_str["success"] = False
        json_str["type"] = "create_task"
        json_str["status"] = "error"
        person_report_topic_msg = {
            "type": "common",
            "text": "很抱歉，无法找到合适的工程师处理问题，请你再次详细描述你的问题和地点，我会尝试给你输出的解决方案。",
            "success": False
        }
        await update_task(task_id, mode=-1, solution=json.dumps(json_str, ensure_ascii=False), report_engineer_id=report_engineer_id)
        if await AsyncMqtt().publish_message(person_report_topic, json.dumps(person_report_topic_msg, ensure_ascii=False)):
            LOG(f"❌ 任务 {task_id} 无法向 {person_report_topic} 推送合适的解决方案.", "DEBUG")


# 由工程师确认任务是否被接受
async def monitor_task_agent(task_id: str, solution: str, engineer_device_id: str, report_device_id: str, title: str,
                             position: str):
    LOG(f"✅ 任务 {task_id} 开始在后台调度运行...", "DEBUG")
    await asyncio.sleep(10)
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
            engineer_topic = f"task/{engineer_device_id}"
            # 自动检测一下位置？
            _engineer_location = (await get_device_detail_by_device_id(engineer_device_id)).location
            _task_location = (await get_task_info_by_id(task_id)).location
            dist = geodesic((_engineer_location.split(";")[0], _engineer_location.split(";")[1]),
                            (_task_location.split(";")[0], _task_location.split(";")[1])).meters
            if dist < 100:
                push_msg = {
                            "type": "common",
                            "ack": True,
                            "msg": "已检测到您到达现场，工单状态已更新为处理中。请按现场规范处理。",
                            "status": "pending",
                            "task_id": task_id
                        }
                await update_task(task_id, mode=2, status=2)
                await wo_update_task_status(task_id, 2)
                if await AsyncMqtt().publish_message(engineer_topic, json.dumps(push_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {task_id} 成功向 {engineer_topic} 推送消息：{push_msg}", "DEBUG")   
            else:
                engineer_msg = {
                    "type": "start_task",
                    "text": f"系统还未检测到您到达现场，请确认是否正在前往{position}。",
                    "task_id": task_id,
                    "status": "pending",
                    "device_id": engineer_device_id
                }
                # 询问师傅是否到达现场并开始工作?
                if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送消息：{engineer_msg}，正在等待工程师确认", "DEBUG")
            await asyncio.sleep(30)
        elif task_info.status == 2:
            engineer_msg = {
                "type": "finish_task",
                "text": "请问该任务是否已处理完成？如已完成，请回复完成。",
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
            if not task_info.completed_photo_path:
                # 请上传完成照片
                engineer_msg = {
                    "type": "upload_finish_task_image",
                    "text": "请在APP上传故障处理完成照片。",
                    "task_id": task_id,
                    "status": "pending",
                    "device_id": engineer_device_id
                }
                engineer_topic = f"task/{engineer_device_id}"
                if await AsyncMqtt().publish_message(engineer_topic, json.dumps(engineer_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {task_id} 成功向工程师 {engineer_topic} 推送消息：{engineer_msg}", "DEBUG")
            await asyncio.sleep(20)
        elif task_info.status == 4:
            push_msg = {
                        "type": "common",
                        "text": f"您反馈的 {title} 已处理完成，工单已闭环。感谢您的反馈。",
                        "status": "finish",
                        "task_id": task_id
                    }
            if await AsyncMqtt().publish_message(f"task/{report_device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 task/{report_device_id} 推送消息：{push_msg}", "DEBUG")
            engineer_topic = f"task/{engineer_device_id}"
            push_msg2 = {
                        "type": "common",
                        "text": f"{title} 已处理完成，工单已闭环。师傅您辛苦了。",
                        "status": "finish",
                        "task_id": task_id
                    }
            if await AsyncMqtt().publish_message(engineer_topic, json.dumps(push_msg2, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 {engineer_topic} 推送消息：{push_msg2}", "DEBUG")
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
    await wo_update_task_status(task_id, -1)
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
        r = redis.Redis(connection_pool=monitor_task_pool)
        if json_str["intention"] == "accept":
            await update_task(self.task_id, mode=2, status=1)
            await wo_update_task_status(self.task_id, 1)
            push_msg = {
                        "type": "common",
                        "ack": True,
                        "msg": f'已为您创建工单，请前往{r.get(f"{self.task_id}_confirm_task_position")}。到达现场后我会自动核验位置。',
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=1)
            await wo_update_task_status(self.task_id, 1)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")
                
            current_task_info = await get_task_info_by_id(self.task_id)
            nickname = (await get_engineer_by_id(current_task_info.engineer_id)).nickname
            push_msg = {
                        "type": "common",
                        "ack": True,
                        "msg": f"已安排{nickname}处理，工单已创建。当前状态：前往中。",
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=1)
            await wo_update_task_status(self.task_id, 1)
            if await AsyncMqtt().publish_message(f"task/{current_task_info.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{current_task_info.device_id} 推送消息：{push_msg}", "DEBUG")
        else:
            push_msg = {
                "type": "common",
                "msg": "未收到确认信息，系统稍后将后发起重新确认请求。",
                "status": "retry",
                "task_id": self.task_id
            }
            await update_task(self.task_id, mode=3)
            if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")
    
    async def start_task(self, confirm_msg: str):
        sys_prompt = f"""
判断用户是否已经到达现场？。返回以下格式的 JSON：

{{
"arrive": "true/false"
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
        if json_str["arrive"] == "true" or json_str["arrive"] is True:
            # 用经纬度计算距离，判断工程师是否真的抵达现场？
            _engineer_location = (await get_device_detail_by_device_id(self.device_id)).location
            _task_location = (await get_task_info_by_id(self.task_id)).location
            dist = geodesic((_engineer_location.split(";")[0], _engineer_location.split(";")[1]),
                            (_task_location.split(";")[0], _task_location.split(";")[1])).meters
            if dist < 100:
                push_msg = {
                            "type": "common",
                            "ack": True,
                            "msg": "已检测到您到达现场，工单状态已更新为处理中。请按现场规范处理。",
                            "status": "pending",
                            "task_id": self.task_id
                        }
                await update_task(self.task_id, mode=2, status=2)
                await wo_update_task_status(self.task_id, 2)
                if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG")     
            else:
                push_msg = {
                    "type": "common",
                    "msg": "工程师还未到达现场，系统稍后将查询最新进度。",
                    "status": "retry",
                    "task_id": self.task_id
                }
                await update_task(self.task_id, mode=3)
                if await AsyncMqtt().publish_message(f"task/{self.device_id}", json.dumps(push_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {self.task_id} 成功向 task/{self.device_id} 推送消息：{push_msg}", "DEBUG") 
        else:
            push_msg = {
                "type": "common",
                "msg": "工程师还未到达现场，系统稍后将查询最新进度。",
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
            # await update_task(self.task_id, mode=2, status=3)
            # await wo_update_task_status(self.task_id, 3)
            push_msg = {
                        "type": "upload_finish_task_image",
                        "ack": True,
                        "msg": "收到完成反馈。请在 App 中上传处理后的现场照片，用于关闭工单。",
                        "status": "pending",
                        "task_id": self.task_id
                    }
            await update_task(self.task_id, mode=2, status=3)
            await wo_update_task_status(self.task_id, 3)
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
    
    async def confirm_task_position(self, confirm_msg: str):
        r = redis.Redis(connection_pool=monitor_task_pool)
        res = await is_legal_position(confirm_msg)
        if res["legal"]:
            r.setex(f"{self.task_id}_confirm_task_position", 60 * 60, res["position"])
        return
            