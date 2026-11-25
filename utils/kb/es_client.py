# -*- coding：utf-8 -*-
"""Elasticsearch 异步客户端（官方 elasticsearch-py 8.x AsyncElasticsearch）。

索引设计：一个向量维度一个索引 {prefix}_{dim}（如 kb_chunk_1024），
所有知识库共享，库间靠 kb_id 字段过滤（与 ragflow 租户级索引同思路）。
中文全文不依赖 ik 插件：入库前 jieba 分词、空格连接存 content_ltks，
查询同样分词后 query_string，分析器用 standard。
"""
import asyncio

from elasticsearch import AsyncElasticsearch

from setting import get_service
from utils.getLogs import kb_logger

_cfg = None
_es: AsyncElasticsearch | None = None
_index_lock = asyncio.Lock()
_ready_indexes: set = set()


def kb_cfg() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = get_service("kb")
    return _cfg


def index_name(dim: int) -> str:
    return f"{kb_cfg()['es_index_prefix']}_{dim}"


async def get_es() -> AsyncElasticsearch:
    global _es
    if _es is None:
        cfg = kb_cfg()
        kwargs = {"hosts": cfg["es_hosts"], "request_timeout": 30}
        if cfg.get("es_user"):
            kwargs["basic_auth"] = (cfg["es_user"], cfg.get("es_password") or "")
        _es = AsyncElasticsearch(**kwargs)
    return _es


async def close_es():
    global _es
    if _es is not None:
        await _es.close()
        _es = None
        _ready_indexes.clear()


def _mapping(dim: int) -> dict:
    return {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "kb_id": {"type": "long"},
                "doc_id": {"type": "long"},
                "docnm_kwd": {"type": "text", "analyzer": "standard"},
                "content_with_weight": {"type": "text", "index": False},
                "content_ltks": {"type": "text", "analyzer": "standard"},
                f"q_{dim}_vec": {
                    "type": "dense_vector", "dims": dim,
                    "index": True, "similarity": "cosine",
                },
                "token_num": {"type": "integer"},
                "position_int": {"type": "integer"},
                "available_int": {"type": "integer"},
                "create_time_flt": {"type": "float"},
                # chunk 配图的对象存储 key 数组（空=无图），检索原样带出
                "img_id": {"type": "keyword", "index": False},
            },
        },
    }


async def ensure_index(dim: int):
    """确保维度索引存在（进程内缓存 + 锁防并发重复建）。

    旧索引动态 strict，缺后加字段会拒写；顺带幂等 put_mapping 补 img_id。
    """
    name = index_name(dim)
    if name in _ready_indexes:
        return
    async with _index_lock:
        if name in _ready_indexes:
            return
        es = await get_es()
        if not await es.indices.exists(index=name):
            try:
                await es.indices.create(index=name, body=_mapping(dim))
            except Exception as e:  # 并发创建竞态：已存在即可
                if "resource_already_exists" not in str(e):
                    raise
        else:
            try:
                await es.indices.put_mapping(
                    index=name, properties={"img_id": {"type": "keyword", "index": False}})
            except Exception as e:
                kb_logger.warning(f"kb 索引 {name} 补 img_id 映射失败: {e}")
        _ready_indexes.add(name)


async def bulk_index(chunks: list, dim: int, refresh: bool = False):
    """chunks: [{kb_id, doc_id, docnm, content, tokens, vec, token_num, position}]"""
    from elasticsearch import helpers as es_helpers
    await ensure_index(dim)
    es = await get_es()
    name = index_name(dim)

    def gen():
        for c in chunks:
            yield {
                "_op_type": "index", "_index": name,
                "kb_id": c["kb_id"], "doc_id": c["doc_id"],
                "docnm_kwd": c["docnm"], "content_with_weight": c["content"],
                "content_ltks": c["tokens"], f"q_{dim}_vec": c["vec"],
                "token_num": c["token_num"], "position_int": c["position"],
                "available_int": 1 if c.get("available", True) else 0,
                "create_time_flt": c.get("create_time_flt", 0.0),
                "img_id": c.get("img_id") or [],
            }

    ops = list(gen())
    if not ops:
        return
    ok, errors = await es_helpers.async_bulk(es, ops, chunk_size=50, refresh=refresh,
                                             stats_only=False)
    if errors:
        raise RuntimeError(f"ES bulk 写入失败 {len(errors)} 条：{errors[0]}")


async def delete_by_doc(doc_id: int, dim: int):
    await ensure_index(dim)
    es = await get_es()
    await es.delete_by_query(index=index_name(dim), refresh=True, conflicts="proceed",
                             body={"query": {"term": {"doc_id": doc_id}}})


async def set_doc_available(doc_id: int, available: bool) -> int:
    """文档启用/停用：全维度索引把它全部 chunk 的 available_int 改掉（检索过滤依据）。

    返回被更新的 chunk 数。维度索引可能没有该文档（未解析），逐个索引容错处理。
    """
    es = await get_es()
    prefix = kb_cfg()["es_index_prefix"]
    updated = 0
    try:
        names = [i for i in (await es.indices.get_alias(index=f"{prefix}_*")).keys()
                 if not i.startswith(".")]
    except Exception:
        return 0
    for name in names:
        try:
            r = await es.update_by_query(index=name, refresh=True, conflicts="proceed",
                                         body={"query": {"term": {"doc_id": doc_id}},
                                               "script": {"source": "ctx._source.available_int = params.a",
                                                          "params": {"a": 1 if available else 0}}})
            updated += r.get("updated", 0)
        except Exception as e:
            if "not_found" not in str(e):
                raise
    return updated


async def delete_by_kb(kb_id: int, dim: int):
    await ensure_index(dim)
    es = await get_es()
    await es.delete_by_query(index=index_name(dim), refresh=True, conflicts="proceed",
                             body={"query": {"term": {"kb_id": kb_id}}})


async def count_by_doc(doc_id: int, dim: int) -> int:
    es = await get_es()
    name = index_name(dim)
    if not await es.indices.exists(index=name):
        return 0
    r = await es.count(index=name, body={"query": {"term": {"doc_id": doc_id}}})
    return r.get("count", 0)


async def search_bm25(query_tokens: str, kb_ids: list, dim: int, size: int = 128) -> list:
    """全文召回：返回 [(chunk_id, score, source)]，score 为原始 BM25。"""
    es = await get_es()
    name = index_name(dim)
    if not await es.indices.exists(index=name):
        return []
    body = {
        "size": size,
        "_source": ["kb_id", "doc_id", "docnm_kwd", "content_with_weight",
                    "token_num", "img_id"],
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"kb_id": kb_ids}},
                    {"term": {"available_int": 1}},
                ],
                "should": [
                    {"match": {"docnm_kwd": {"query": query_tokens, "boost": 5}}},
                    {"query_string": {
                        "query": query_tokens, "fields": ["content_ltks^1"],
                        "default_operator": "OR", "minimum_should_match": "30%",
                        "boost": 1,
                    }},
                ],
            }
        },
    }
    r = await es.search(index=name, body=body)
    return [(h["_id"], h["_score"], h.get("_source", {})) for h in r["hits"]["hits"]]


async def search_knn(vector: list, kb_ids: list, dim: int, size: int = 128) -> list:
    """向量召回：返回 [(chunk_id, score, source)]，score 为 ES cosine 得分 (1+cos)/2。"""
    es = await get_es()
    name = index_name(dim)
    if not await es.indices.exists(index=name):
        return []
    body = {
        "size": size,
        "_source": ["kb_id", "doc_id", "docnm_kwd", "content_with_weight",
                    "token_num", "img_id"],
        "knn": {
            "field": f"q_{dim}_vec",
            "query_vector": vector,
            "k": size,
            "num_candidates": max(size * 4, 100),
            "filter": [
                {"terms": {"kb_id": kb_ids}},
                {"term": {"available_int": 1}},
            ],
        },
    }
    r = await es.search(index=name, body=body)
    return [(h["_id"], h["_score"], h.get("_source", {})) for h in r["hits"]["hits"]]


async def list_chunks_by_doc(doc_id: int, dim: int, page: int = 1, size: int = 20,
                             offset: int = None):
    # offset 与 page 两种分页语义（offset 优先）：后台页用 page；外部契约用
    # offset/limit（非整页倍数时 page 换算不出来，如 offset=5 limit=10）
    es = await get_es()
    name = index_name(dim)
    if not await es.indices.exists(index=name):
        return {"rows": [], "total": 0}
    frm = offset if offset is not None else (page - 1) * size
    body = {
        "from": frm, "size": size, "track_total_hits": True,
        "sort": [{"position_int": "asc"}],
        "_source": ["doc_id", "content_with_weight", "token_num", "position_int", "available_int"],
        "query": {"term": {"doc_id": doc_id}},
    }
    r = await es.search(index=name, body=body)
    rows = [{"chunk_id": h["_id"], **h.get("_source", {})} for h in r["hits"]["hits"]]
    total = r["hits"]["total"]["value"] if isinstance(r["hits"]["total"], dict) else r["hits"]["total"]
    return {"rows": rows, "total": total}
