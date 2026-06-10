import json
import time
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
        extra_body={"chat_template_kwargs": {"enable_thinking": True}, "top_k": 20, "min_p": 0},
        temperature=0.6,
        top_p=0.95
    )
    response = completion.choices[0].message.content
    _json_str = extract_json_from_response(response)
    return _json_str


async def is_legal_position(question: str):
    sys_prompt = f"""
    判断用户提供的是否是一个合法的地点？
    返回以下格式的 JSON：
    {{
        "legal": true/false,
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


if __name__ == "__main__":
    import asyncio
    # print(asyncio.run(get_user_intention("你爱我吗？")))
    print(asyncio.run(is_legal_position("14号冷却塔")))