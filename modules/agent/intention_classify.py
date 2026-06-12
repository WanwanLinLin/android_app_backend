import json
import time
from typing import List
import aiohttp
import requests
from datetime import datetime
from openai import AsyncOpenAI
from setting import config_data
from utils.tools import extract_json_from_response


async def get_user_intention(question: str):
    sys_prompt = f"""
    分析用户的意图，并识别任务地点：
    1.卫生处理: 例如地面积水、垃圾堆放、公共区域污渍、异味清理等。
    2.故障报修: 例如设备异响、照明损坏、空调异常、电梯/门禁/水电设施故障等。
    3.安全事件: 例如人员冲突、可疑人员、消防隐患、通道堵塞、车辆/秩序异常等。
    4.undefied: 未识别到的意图类型
    返回以下格式的 JSON：
    {{
        "type": "识别结果",
        "position": "识别到的地点，如果不存在则为 undefied"
    }}
    """

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
            {"role": "user", "content": question},
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    return json.loads(_json_str, strict=False)


async def is_legal_position(question: str):
    sys_prompt = f"""
    判断用户提供的是否是一个合法的地点？
    返回以下格式的 JSON：
    {{
        "legal": true/false,
        "position": "识别到的地点名称，如果不存在则为 undefied"
    }}
    """

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
            {"role": "user", "content": question},
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    return json.loads(_json_str, strict=False)


async def order_floor(floor_ids: List, floor_name: List):
    question = f"""
这是楼层名称列表：{floor_name}，
对应的楼层id列表：{floor_ids}
按照楼层的高度从上到下排序，返回排序后的楼层id列表，
请返回以下格式的 JSON：
{{
  "floor_ids": [排序正确的楼层id列表(int)]
}}
"""

    llm_client = AsyncOpenAI(
        base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
        api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
        timeout=60,
        max_retries=3
    )
    completion = await llm_client.chat.completions.create(
        model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
        messages=[
            {"role": "user", "content": question},
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    return json.loads(_json_str, strict=False)


async def determine_inspection_way(floor_ids: List, floor_name: List,
                                   check_floor_ids: List, check_floor_name: List):
    question = f"""
现在有一个巡检任务，保安必须要按目的地名称列表顺序进行巡检，你需要校验保安当前的巡检路径是否正确，
目的地名称列表：{list(set(floor_name))},
目的地id列表：{list(set(floor_ids))},
保安当前已经巡视的名称列表：{list(set(check_floor_name))},
保安当前已经巡视的id列表：{list(set(check_floor_ids))},
请返回以下格式的 JSON：
{{
  "correct": true/false
  "reason": "正确或者错误的原因。"
  "floor_ids": [纠正后的保安当前已经巡视的id列表(int)],
  "next_position": "下一个巡检的目的地名称"
}}
注意：
1.如果保安一开始没有按照目的地名称列表进行巡检，那么floor_ids应该直接清空，并且next_position为第一个目的地名称
2.如果保安中途巡视目的地顺序错误，那么floor_ids仅保留先前巡检正确的目的地id，next_position应该为下一个正确的目的地名称。
3.目的地名称列表与目的地id列表是按顺序一一对应的，请注意识别
"""

    llm_client = AsyncOpenAI(
        base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["base_url"],
        api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["apikey"],
        timeout=60,
        max_retries=3
    )
    completion = await llm_client.chat.completions.create(
        model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Qwen3-32B-AWQ"]["model"],
        messages=[
            {"role": "user", "content": question},
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    return json.loads(_json_str, strict=False)


if __name__ == "__main__":
    import asyncio
    # print(asyncio.run(get_user_intention("你爱我吗？")))
    print(asyncio.run(is_legal_position("14号冷却塔")))