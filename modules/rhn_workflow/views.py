# -*- coding: utf-8 -*-
"""18066 数字人工作流的文档知识库适配层。

契约：logs/documents/knowledge-provider.openapi.yaml（三个接口，裸 JSON、无 code/msg/data 壳）：
  GET  /v1/knowledge                                  库目录（工作流过滤 deleting，恒 false）
  POST /v1/search/compare                             跨库检索，合计 top_k，单库故障不阻断
  GET  /v1/knowledge/{kid}/documents/{did}/chunks     按 offset/limit 读块（提取首块"原文："网址）

口径说明：
  - knowledge_id：契约要求 slug（^[a-z0-9][a-z0-9_-]{0,63}$），本平台库 ID 为自增
    int，直接以十进制字符串对外（"7" 合法通过该正则）；非数字 slug 本平台不存在。
  - 鉴权：账号级 API Key（Bearer sk-xxx，utils/api_key_auth），可见范围 = key 归属
    者自建的库。不复用全局 JwtAuthError 处理器（它回 HTTP 200 + body code 401，
    工作流按 HTTP 状态码判定会误判成功），这里统一改抛 HTTPException(401)；
    库不存在/不属于该 key 一律 404，不泄露存在性。
  - 逐库容错：按库并行调 retrieval（单库单查询，天然规避跨库维度一致限制），
    某库异常只在该库 results 里记 ok=false，命中按相似度跨库合并截断 top_k。
  - sources[].section：chunk 未存章节名，省略（契约 sources 无必填字段，工作流
    仅按第一个来源展示文档名，document_name 已给）。
  - content：直接给 chunk 原文，不拼"原文："行（本平台为上传文档库，无 URL 出处；
    工作流仅在正文缺"原文："行时放弃补链，不影响检索问答）。
"""
import asyncio
import re
from typing import Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from . import schema
from mybatisPlus import kb_orm
from utils.api_key_auth import current_api_key
from utils.apierror import JwtAuthError
from utils.getLogs import kb_logger
from utils.kb import es_client
from utils.kb.retrieval import retrieval

router = APIRouter()

_KID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _kid_to_id(kid) -> Union[int, None]:
    """契约 knowledge_id（slug 字符串）→ 本平台自增库 ID；非法/非数字返回 None。"""
    s = str(kid or "")
    if not _KID_RE.match(s):
        return None
    return int(s) if s.isdigit() else None


async def bearer_api_key(Authorization: str = Header(default=None)):
    """与 current_api_key 同口径，但失败回 HTTP 401（契约要求，全局处理器回 200）。"""
    try:
        return await current_api_key(Authorization=Authorization)
    except JwtAuthError:
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


def _kb_owned(kb: Union[dict, None], key: dict) -> bool:
    return bool(kb) and kb.get("created_by") == key.get("created_by")


# ---------------- 库目录 ----------------

@router.get("/v1/knowledge", summary="[RHN工作流] 获取可选文档库", tags=["RHN工作流"])
async def list_knowledge_libraries(key: dict = Depends(bearer_api_key)):
    ds = await kb_orm.list_datasets(admin_id=key["created_by"], is_admin=False)
    # deleting：本平台删除为同步软删，无"删除中"中间态，恒 false（工作流按此过滤）
    libraries = [{"knowledge_id": str(d["id"]), "name": d["name"] or str(d["id"]),
                  "deleting": False} for d in ds["rows"]]
    return {"libraries": libraries}


# ---------------- 跨库检索 ----------------

@router.post("/v1/search/compare", summary="[RHN工作流] 指定库检索并跨库排序", tags=["RHN工作流"])
async def search_compare(info: schema.CompareModel, key: dict = Depends(bearer_api_key)):
    metas, results = [], []
    for kid in info.knowledge_ids:
        kb_id = _kid_to_id(kid)
        kb = await kb_orm.get_dataset(kb_id) if kb_id else None
        if not kb:
            results.append({"knowledge_id": kid, "ok": False, "error": "知识库不存在"})
            continue
        if not _kb_owned(kb, key):
            results.append({"knowledge_id": kid, "ok": False, "error": "知识库不属于该 API Key"})
            continue
        metas.append({"kid": kid, "dim": kb["embd_dim"],
                      "vsw": kb["vector_similarity_weight"],
                      "rl": kb.get("rerank_limit")})

    async def _one(m):
        return await retrieval(info.question,
                               [{"kb_id": int(m["kid"]), "dim": m["dim"],
                                 "vsw": m["vsw"], "rl": m["rl"]}],
                               page=1, size=info.top_k)

    # return_exceptions=True 是"单库故障返回其它库命中"的关键；gather 保序，
    # 与 metas 一一对应回填 results
    outs = await asyncio.gather(*(_one(m) for m in metas), return_exceptions=True)

    merged = []
    for m, out in zip(metas, outs):
        if isinstance(out, Exception):
            kb_logger.error(f"rhn_workflow 库 {m['kid']} 检索失败: {out}")
            results.append({"knowledge_id": m["kid"], "ok": False, "error": str(out)})
            continue
        results.append({"knowledge_id": m["kid"], "ok": True})
        for c in out.get("chunks", []):
            merged.append({
                "content": c.get("content", ""),
                "score": c.get("similarity"),
                "sources": [{"knowledge_id": m["kid"],
                             "document_id": str(c.get("doc_id")),
                             "document_name": c.get("document_name")}],
                "_sim": c.get("similarity") or 0.0,
            })
    # 跨库重排：各库相似度同口径（同 vsw 公式+同 rerank），可直接全局排序
    merged.sort(key=lambda x: x["_sim"], reverse=True)
    hits = [{k: v for k, v in h.items() if k != "_sim"} for h in merged[:info.top_k]]

    errors = [r for r in results if not r["ok"]]
    return {
        "hits": hits,
        "ranking_status": "failed" if metas and not any(
            r["ok"] for r in results) else "ready",  # 全部在检库都失败才 failed
        "warning": "；".join(f"{r['knowledge_id']}：{r['error']}" for r in errors) or None,
        "results": results,
    }


# ---------------- 文档分块（补原文网址） ----------------

@router.get("/v1/knowledge/{knowledge_id}/documents/{document_id}/chunks",
            summary="[RHN工作流] 读取文档分块", tags=["RHN工作流"])
async def get_document_chunks(knowledge_id: str, document_id: str,
                              offset: int = Query(0, ge=0),
                              limit: int = Query(1, ge=1, le=100),
                              key: dict = Depends(bearer_api_key)):
    kb_id = _kid_to_id(knowledge_id)
    kb = await kb_orm.get_dataset(kb_id) if kb_id else None
    if not kb or not _kb_owned(kb, key):
        raise HTTPException(status_code=404, detail="document not found")
    if not document_id.isdigit():
        raise HTTPException(status_code=404, detail="document not found")
    doc = await kb_orm.get_document(int(document_id))
    if not doc or doc.get("kb_id") != kb_id:
        raise HTTPException(status_code=404, detail="document not found")
    data = await es_client.list_chunks_by_doc(int(document_id), kb["embd_dim"],
                                              offset=offset, size=limit)
    # position_int 升序 + from=offset：工作流 offset=0/limit=1 即取首块提"原文："网址
    return {"chunks": [{"content": r.get("content_with_weight", "")}
                       for r in data.get("rows", [])]}
