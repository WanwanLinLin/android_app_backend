# -*- coding: utf-8 -*-
from typing import List, Union
from pydantic import BaseModel


class AddKbModel(BaseModel):
    name: str
    desc: Union[str, None] = None
    embd_id: Union[str, None] = None  # 缺省用 config kb.embedding.default
    chunk_token_num: Union[int, None] = 256
    similarity_threshold: Union[float, None] = 0.2
    vector_similarity_weight: Union[float, None] = 0.3
    parser_id: Union[str, None] = "General"  # 默认切片方法（文档未单独指定时继承）
    rerank_limit: Union[int, None] = 64  # 检索命中候选上限（8~256）


class UpdateKbModel(BaseModel):
    name: Union[str, None] = None
    desc: Union[str, None] = None
    chunk_token_num: Union[int, None] = None
    similarity_threshold: Union[float, None] = None
    vector_similarity_weight: Union[float, None] = None
    parser_id: Union[str, None] = None
    rerank_limit: Union[int, None] = None


class DocAvailableModel(BaseModel):
    available: bool


class DocParserModel(BaseModel):
    parser_id: str  # 切片方法：General|Q&A|Manual|Paper|Book|Laws|One|Tag


class OpenRetrievalModel(BaseModel):
    """对外检索接口入参（API Key 鉴权，只能查 key 归属者自建的库）。"""
    kb_ids: Union[List[int], None] = None  # 不传=归属者全部库；传则取交集校验归属
    question: str
    page: Union[int, None] = 1
    size: Union[int, None] = 10
    similarity_threshold: Union[float, None] = None
    vector_similarity_weight: Union[float, None] = None


class KbRetrievalModel(BaseModel):
    kb_ids: List[int]
    question: str
    page: Union[int, None] = 1
    size: Union[int, None] = 10
    similarity_threshold: Union[float, None] = None  # 不传用各库配置
    vector_similarity_weight: Union[float, None] = None
