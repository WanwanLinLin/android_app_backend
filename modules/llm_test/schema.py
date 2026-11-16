# -*- coding: utf-8 -*-
from typing import List, Union
from pydantic import BaseModel


class RuleModel(BaseModel):
    type: str  # contains | not_contains | regex | llm_judge
    value: str


class AddLlmTestTaskModel(BaseModel):
    name: str
    desc: Union[str, None] = None
    plugin_ids: List[int]
    test_prompts: Union[List[str], None] = None  # 多轮问题，同一会话按序提问，最多10个
    rules: Union[List[RuleModel], None] = None
    schedule_enabled: Union[bool, None] = None
    schedule_time: Union[str, None] = None  # "YYYY-MM-DD HH:MM:SS"（北京时间，首次运行；之后每天重复）


class UpdateLlmTestTaskModel(BaseModel):
    name: Union[str, None] = None
    desc: Union[str, None] = None
    plugin_ids: Union[List[int], None] = None
    test_prompts: Union[List[str], None] = None
    rules: Union[List[RuleModel], None] = None
    schedule_enabled: Union[bool, None] = None
    schedule_time: Union[str, None] = None
