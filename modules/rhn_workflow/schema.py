# -*- coding: utf-8 -*-
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator


class CompareModel(BaseModel):
    """POST /v1/search/compare 入参（18066 工作流契约）。

    约束由 pydantic 把守，违规 FastAPI 自动回 422：question 1~2000 字；
    knowledge_ids 1~10 个且不可重复（契约 uniqueItems: true）；mode 仅 global；
    top_k 为所有库合计返回的最大命中数。
    """
    question: str = Field(..., min_length=1, max_length=2000)
    knowledge_ids: List[str] = Field(..., min_length=1, max_length=10)
    mode: Literal["global"]
    top_k: int = Field(..., ge=1, le=50)

    @field_validator("knowledge_ids")
    @classmethod
    def _unique(cls, v):
        # 重复 ID 属参数无效（422），不去重静默通过
        if len(set(v)) != len(v):
            raise ValueError("knowledge_ids must have unique items")
        return v
