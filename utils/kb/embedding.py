# -*- coding：utf-8 -*-
"""嵌入向量客户端：openai 兼容 /embeddings 接口（Xinference、vLLM 等均可）。

配置在 config.yaml kb.embedding.models，键即模型标识（存 KbDataset.embd_id）。
批量 + 单并发锁内串行提交（NPU 服务并发能力有限），失败重试 1 次。
"""
import asyncio

import httpx
from openai import AsyncOpenAI

from utils.kb.es_client import kb_cfg

_clients: dict = {}
_model_locks: dict = {}


def get_model_conf(embd_id: str = None) -> dict:
    emb = kb_cfg()["embedding"]
    key = embd_id or emb["default"]
    models = emb.get("models") or {}
    if key not in models:
        raise ValueError(f"未登记的嵌入模型: {key}（config.yaml kb.embedding.models）")
    return models[key]


def _client(embd_id: str) -> AsyncOpenAI:
    if embd_id not in _clients:
        conf = get_model_conf(embd_id)
        _clients[embd_id] = AsyncOpenAI(
            base_url=conf["base_url"], api_key=conf.get("apikey") or "none",
            timeout=httpx.Timeout(60.0), max_retries=0)
        _model_locks[embd_id] = asyncio.Lock()
    return _clients[embd_id]


async def embed_texts(texts: list, embd_id: str = None, batch_size: int = 16) -> list:
    """返回与 texts 等长的向量列表；任一失败（重试后）抛异常，由调用方置文档失败。"""
    if not texts:
        return []
    conf = get_model_conf(embd_id)
    key = embd_id or kb_cfg()["embedding"]["default"]
    client = _client(key)
    vectors: list = []
    async with _model_locks[key]:
        for i in range(0, len(texts), batch_size):
            batch = [t if t.strip() else " " for t in texts[i:i + batch_size]]
            last_err = None
            for _ in range(2):
                try:
                    resp = await client.embeddings.create(
                        model=conf["model"], input=batch)
                    vectors.extend(d.embedding for d in resp.data)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.5)
            if last_err:
                raise RuntimeError(f"embedding 调用失败: {last_err}")
    return vectors


async def embed_query(text: str, embd_id: str = None) -> list:
    return (await embed_texts([text], embd_id))[0]
