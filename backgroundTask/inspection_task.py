import sys
sys.path.append("../")

import json
import asyncio
from setting import config_data
from utils.getLogs import LOG
from utils.async_mqtt_client import AsyncMqtt
from mybatisPlus.work_order_inspection_orm import (wo_get_all_unstart_tasks, wo_order_inspection_floors,
                                                   wo_get_inspection_info_by_task_id, wo_update_inspection_check_floors_ids, wo_update_inspection_process_msg, wo_update_inspection_status)
from datetime import datetime, timedelta
from modules.agent.intention_classify import order_floor, determine_inspection_way

PENDING_TASKS = []


async def monitor_inspection_workflow(task_id: str):
    LOG(f"开始监听任务：{task_id}", "DEBUG")
    # 首先修正楼层顺序
    inspection_info = await wo_get_inspection_info_by_task_id(task_id)
    order_res = await order_floor(inspection_info["floor_ids"], inspection_info["floor_name"])
    await wo_order_inspection_floors(task_id, order_res["floor_ids"])
    LOG(f"巡检楼层顺序修改成功！：{order_res}", "DEBUG")
    inspection_info = await wo_get_inspection_info_by_task_id(task_id)
    inspection_start_time = inspection_info["start_time"]
    # 提醒巡检员确认任务
    while inspection_info["status"] == 0 and (datetime.strptime(inspection_info["start_time"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() / 60 < 60:
        if (datetime.strptime(inspection_info["start_time"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() / 60 < 5:
            person_report_topic_msg = {
                "type": "confirm_inspection_task",
                "text": f"距离你今日的巡检任务开始时间仅剩5分钟了，请在APP上确认你的巡检任务。",
                "task_id": task_id
            }
            if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
        elif (datetime.now() - datetime.strptime(inspection_info["start_time"], "%Y-%m-%d %H:%M:%S")).total_seconds() > 0:
            person_report_topic_msg = {
                "type": "confirm_inspection_task",
                "text": f"巡检任务已超过提醒时间，请尽快开始。若无法执行，请回复原因。",
                "task_id": task_id
            }
            if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
        await asyncio.sleep(30)
        inspection_info = await wo_get_inspection_info_by_task_id(task_id)
    
    person_report_topic_msg = {
                "type": "common",
                "text": f'好的，巡检任务已开始。请先前往{inspection_info["floor_name"][0]}完成NFC感应。',
                "task_id": task_id
    }
    if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
        LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
    await asyncio.sleep(10)
    
    inspection_info = await wo_get_inspection_info_by_task_id(task_id)
    # 开始监控任务(1个小时以内要完成)
    while inspection_info["status"] == 1 and (datetime.strptime(inspection_info["start_time"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() / 60 < 60:
        inspection_info = await wo_get_inspection_info_by_task_id(task_id)
        if set(inspection_info["floor_ids"]) == set(inspection_info["checked_floor_ids"]):
            # 巡检任务完成
            await wo_update_inspection_status(task_id, 2)
            person_report_topic_msg = {
                "type": "common",
                "text": f'{inspection_info["floor_name"][-1]}点位已记录，本次巡检已完成。感谢您完成今日巡检任务。',
                "task_id": task_id
            }
            if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
                LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
            return
        elif inspection_info["checked_floor_ids"]:
            res = await determine_inspection_way(inspection_info["floor_ids"], inspection_info["floor_name"],
                                                    inspection_info["checked_floor_ids"], inspection_info["checked_floor_name"])
            if not res["correct"]:
                person_report_topic_msg = {
                    "type": "common",
                    "text": f'当前点位顺序不正确，请先完成{res["next_position"]}后再继续。',
                    "task_id": task_id
                }
                if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
                await wo_update_inspection_check_floors_ids(task_id, res["floor_ids"])
                await wo_update_inspection_process_msg(task_id, res["reason"])
            else:
                person_report_topic_msg = {
                    "type": "common",
                    "text": f'{inspection_info["checked_floor_name"][-1]}点位已记录，请继续前往{res["next_position"]}。',
                    "task_id": task_id
                }
                if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
                    LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
        # 每隔30秒检查一次状态
        await asyncio.sleep(30)
    await wo_update_inspection_status(task_id, -1)
    person_report_topic_msg = {
        "type": "common",
        "text": f"今日巡检任务超时未完成，请关注。",
        "task_id": task_id
    }
    if await AsyncMqtt().publish_message(f"task/{inspection_info['device_ids'][0]}", json.dumps(person_report_topic_msg, ensure_ascii=False)):
        LOG(f"✅ 任务 {task_id} 成功向 task/{inspection_info['device_ids'][0]} 推送巡检消息. {person_report_topic_msg}", "DEBUG")
    PENDING_TASKS.remove(task_id)


async def main():
    LOG("Inspection Task Start", "DEBUG")
    try:
        while 1:
            # LOG("Waiting for inspection task", "DEBUG")
            pending_tasks = await wo_get_all_unstart_tasks()
            if pending_tasks:
                for pt in pending_tasks:
                    if pt["task_id"] not in PENDING_TASKS:
                        try:
                            if (datetime.strptime(pt["start_time"], "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() / 60 < 5:
                                PENDING_TASKS.append(pt["task_id"])
                                asyncio.create_task(monitor_inspection_workflow(pt["task_id"]))
                        except Exception as e:
                            LOG(f'任务 {pt["task_id"]} 报错：{e}', "DEBUG")
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(5)
    except KeyboardInterrupt:
        LOG("Inspection Task Disconnect", "DEBUG")
    return


if __name__ == "__main__":
    asyncio.run(main())