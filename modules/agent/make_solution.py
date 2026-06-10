import json
import time
import aiohttp
import requests
from datetime import datetime
from openai import AsyncOpenAI
from setting import config_data
from utils.getLogs import LOG
from utils.tools import extract_json_from_response


async def get_perfect_solution(event_description: str, position: str):
    sys_prompt = f"""
现在是北京时间：{datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')}，当前经纬度位置 {position}，
根据用户提出的问题，从工程师列表中挑选出最适合解决该问题且距离当前位置最近的工程师列表，并给出解决方案。返回以下格式的 JSON：

{{
  "ids": [工程师id列表(int)],
  "names": [工程师名称列表(str)],
  "distance": [工程师距离列表(float,单位为米)],
  "title": "任务标题（简短概括任务目标）"
  "solution": "解决方案",
  "start_time": "根据距离给出合理的开始解决时间，格式: %Y-%m-%d %H:%M:%S"
}}
注意：
- 需要仔细分析用户的意图，拆分出需要解决的问题个数
- 每个问题尽可能只找一位工程师解决问题，无需考虑备选工程师
- 解决方案中的地点名称不能是经纬度
- 解决方案中必须包含事故可能的原因、工程师名字、目标地点以及开始解决时间
- 任何因为用户意图不明确导致无法找到合适的解决方案的情况，所有的字段都返回null
- 如果解决方案中有多位相同职责的工程师并且距离相近，只需要实际距离最近的那一位
- 对于某个无法提出合适的解决方案的问题，直接在返回结果中返回相应的具体原因即可。
"""

    user_prompt = f"用户提出的问题：{event_description}"
    llm_client = AsyncOpenAI(
        base_url=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Hermes-Agent"]["base_url"],
        api_key=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Hermes-Agent"]["apikey"],
        timeout=60,
        max_retries=3
    )
    completion = await llm_client.chat.completions.create(
        model=config_data["THIRD_PARTY_SERVICES"][0]["generic_llm"]["Hermes-Agent"]["model"],
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
    return json.loads(_json_str, strict=False)