# -*- coding：utf-8 -*-
"""混合检索：BM25 全文 + KNN 向量并行召回，融合打分后按阈值截断。

打分口径（对齐 ragflow retrieval 语义，便于终端/对话侧无缝切换）：
    score = (1 - vsw) * norm_bm25 + vsw * vcos
其中 vcos 直接用 ES 的 cosine 得分 (1+cos)/2 ∈ [0,1]；bm25 按本次召回最大分归一。
可选 rerank（config kb.rerank.enabled）：vLLM Qwen3-rerank /rerank 接口，
失败自动回退纯混合分，不阻断检索。
"""
import asyncio

import httpx

from utils.getLogs import kb_logger
from utils.kb import es_client
from utils.kb.embedding import embed_query
from utils.kb.es_client import kb_cfg
from utils.kb.tokenizer import build_query_string


async def _rerank(question: str, docs: list, top_len: int) -> dict | None:
    """调外部 rerank 模型，返回 {doc_index: score∈[0,1]}；任何异常返回 None（回退）。"""
    cfg = kb_cfg().get("rerank") or {}
    if not cfg.get("enabled") or not docs:
        return None
    payload = {
        "model": cfg.get("model", "Qwen3-Reranker-4B"),
        "query": question[:top_len],
        "documents": [d[:top_len] for d in docs],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            r = await client.post(cfg["url"], json=payload)
            r.raise_for_status()
            results = r.json().get("results") or r.json().get("data") or []
            out = {}
            for item in results:
                idx = item.get("index", item.get("document"))
                rel = item.get("relevance_score", item.get("score"))
                if idx is not None and rel is not None:
                    out[int(idx)] = float(rel)
            return out or None
    except Exception as e:
        kb_logger.info(f"kb rerank 失败，回退混合分: {e}")
        return None


async def retrieval(question: str, kb_metas: list, page: int = 1, size: int = 10,
                    similarity_threshold: float = None,
                    vector_similarity_weight: float = None,
                    rerank_limit: int = None) -> dict:
    """kb_metas: [{"kb_id":..,"dim":..,"vsw":..,"rl":..}]（同一维度才可跨库联查，视图层保证）。

    rerank_limit（命中候选上限）优先用入参，其次取各库配置的最大值，兜底 64。
    返回 {"chunks":[...], "total":n, "vector_similarity_weight":...}
    """
    if not kb_metas or not (question or "").strip():
        return {"chunks": [], "total": 0}
    dims = {m["dim"] for m in kb_metas}
    if len(dims) != 1:
        raise ValueError("跨知识库检索要求各库向量维度一致")
    dim = dims.pop()
    kb_ids = [m["kb_id"] for m in kb_metas]
    vsw = vector_similarity_weight
    if vsw is None:
        vs = [m.get("vsw") for m in kb_metas if m.get("vsw") is not None]
        vsw = sum(vs) / len(vs) if vs else 0.3
    thr = similarity_threshold if similarity_threshold is not None else 0.2
    # 命中候选上限：入参 > 各库配置(取最大) > config kb.rerank.limit > 64，
    # 最终归一到 32/48/64 三档（就近取档）
    if rerank_limit is None:
        rls = [m.get("rl") for m in kb_metas if m.get("rl")]
        cfg_rl = (kb_cfg().get("rerank") or {}).get("limit")
        rerank_limit = max(rls) if rls else (cfg_rl or 64)
    rerank_limit = min((32, 48, 64), key=lambda x: (abs(x - int(rerank_limit)), x))

    q_tokens = build_query_string(question)
    # 召回阶段多取：BM25/KNN 各 rerank_limit*2，融合后截断
    recall = max(rerank_limit * 2, size * 4)
    vec = await embed_query(question)
    bm_hits, knn_hits = await asyncio.gather(
        es_client.search_bm25(q_tokens, kb_ids, dim, recall),
        es_client.search_knn(vec, kb_ids, dim, recall))

    merged: dict = {}  # chunk_id -> [bm25, vcos, source]
    for cid, score, src in bm_hits:
        merged.setdefault(cid, [0.0, 0.0, src])[0] = score
    for cid, score, src in knn_hits:
        m = merged.setdefault(cid, [0.0, 0.0, src])
        m[1] = score
        if not m[2]:
            m[2] = src
    if not merged:
        return {"chunks": [], "total": 0, "vector_similarity_weight": vsw}

    max_bm = max(v[0] for v in merged.values()) or 1.0
    items = []
    for cid, (bm, vc, src) in merged.items():
        sim = (1 - vsw) * (bm / max_bm) + vsw * vc
        items.append({"chunk_id": cid, "bm25": bm, "vcos": vc, "sim": sim, "src": src})
    items.sort(key=lambda x: x["sim"], reverse=True)
    items = items[:rerank_limit]

    rerank_scores = await _rerank(
        question, [it["src"].get("content_with_weight", "") for it in items],
        (kb_cfg().get("rerank") or {}).get("top_len", 512))
    if rerank_scores:
        for i, it in enumerate(items):
            rs = rerank_scores.get(i)
            if rs is not None:
                it["sim"] = 0.5 * rs + 0.5 * it["sim"]
        items.sort(key=lambda x: x["sim"], reverse=True)

    passed = [it for it in items if it["sim"] >= thr]
    total = len(passed)
    page_items = passed[(page - 1) * size: page * size]
    chunks = [{
        "chunk_id": it["chunk_id"],
        "kb_id": it["src"].get("kb_id"),
        "doc_id": it["src"].get("doc_id"),
        "document_name": it["src"].get("docnm_kwd"),
        "content": it["src"].get("content_with_weight", ""),
        "similarity": round(it["sim"], 4),
        "vector_similarity": round(it["vcos"], 4),
        "term_similarity": round(it["bm25"], 4),
    } for it in page_items]
    return {"chunks": chunks, "total": total, "vector_similarity_weight": vsw}
