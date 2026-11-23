# -*- coding：utf-8 -*-
"""文档解析后台任务：MinIO 取文件 → 抽文本 → 分块 → 向量化 → ES 写入 → 计数回写。

全部在 FastAPI 进程内以 asyncio 任务执行（lifespan 起协程，无额外进程）：
  - CPU/同步 IO（pdf/docx 解析、分块）经 asyncio.to_thread 卸载
  - 网络 IO（embedding、ES、MinIO）本身异步
  - 全局信号量限制同时解析文档数，防 embedding/ES 被打爆
重解析语义：先删该文档旧 chunk 再全量写入（chunk 计数按新旧差值回写库级）。
"""
import asyncio
import time

from utils.getLogs import kb_logger
from utils.kb import es_client, minio_client
from utils.kb.embedding import embed_texts
from utils.kb.parser import extract_text, split_chunks
from utils.kb.es_client import kb_cfg

_sem: asyncio.Semaphore | None = None
_tasks: set = set()  # 持有任务引用防 GC


def _get_sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(kb_cfg().get("max_concurrent_parse", 2) or 2)
    return _sem


def spawn_parse(doc_id: int):
    """投递解析任务（视图层调用）。同一文档重复投递由 DB 状态 run==1 挡重。"""
    t = asyncio.create_task(parse_document(doc_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return t


async def parse_document(doc_id: int):
    from mybatisPlus import kb_orm

    async with _get_sem():
        doc = await kb_orm.get_document(doc_id)
        if not doc:
            kb_logger.error(f"kb 解析任务找不到文档 #{doc_id}")
            return
        kb = await kb_orm.get_dataset(doc["kb_id"])
        if not kb:
            await kb_orm.set_document_parse_state(doc_id, -1, -1, "知识库不存在")
            return
        embd_id, dim = kb["embd_id"], kb["embd_dim"]
        chunk_num_cfg = (doc.get("parser_config") or {}).get("chunk_token_num") \
            or kb["chunk_token_num"] or 256
        parser_id = doc.get("parser_id") or "General"
        try:
            await kb_orm.set_document_parse_state(doc_id, 1, 0.05, "读取文件…")
            data = await minio_client.get_object(doc["location"])

            await kb_orm.set_document_parse_state(doc_id, 1, 0.2, "解析文本…")
            text = await asyncio.to_thread(extract_text, data, doc["file_type"])
            chunks = await asyncio.to_thread(split_chunks, text, chunk_num_cfg, parser_id)
            if not chunks:
                # 空文档：清旧 chunk 后直接完成
                await es_client.delete_by_doc(doc_id, dim)
                await kb_orm.finish_document(doc_id, doc["kb_id"], 0, 0)
                await kb_orm.set_document_parse_state(doc_id, 3, 1.0, "文档无有效文本内容")
                return

            await kb_orm.set_document_parse_state(doc_id, 1, 0.3,
                                                  f"抽取 {len(chunks)} 个分块，向量化中…")
            texts = [c[0] for c in chunks]
            vectors = []
            step = 16
            for i in range(0, len(texts), step):
                vectors.extend(await embed_texts(texts[i:i + step], embd_id))
                prog = 0.3 + 0.6 * min(1.0, (i + step) / len(texts))
                await kb_orm.set_document_parse_state(doc_id, 1, round(prog, 2),
                                                      f"向量化 {min(i + step, len(texts))}/{len(texts)}")

            await kb_orm.set_document_parse_state(doc_id, 1, 0.95, "写入索引…")
            now = time.time()
            docs = [{
                "kb_id": doc["kb_id"], "doc_id": doc_id, "docnm": doc["name"],
                "content": c[0], "tokens": _tok(c[0]), "vec": v,
                "token_num": c[1], "position": c[2], "create_time_flt": now,
                # 文档若处于停用状态，重解析后 chunk 仍保持不可检索
                "available": doc.get("available", True),
            } for c, v in zip(chunks, vectors)]
            # 先删旧再写新：重解析不残留
            await es_client.delete_by_doc(doc_id, dim)
            await es_client.bulk_index(docs, dim, refresh=True)
            await kb_orm.finish_document(doc_id, doc["kb_id"], len(chunks),
                                         sum(c[1] for c in chunks))
            await kb_orm.set_document_parse_state(
                doc_id, 3, 1.0, f"完成：{len(chunks)} chunks")
            kb_logger.info(f"kb 文档 #{doc_id}（{doc['name']}）解析完成，{len(chunks)} chunks")
        except Exception as e:
            kb_logger.error(f"kb 文档 #{doc_id} 解析失败: {e}")
            try:
                await kb_orm.set_document_parse_state(doc_id, -1, -1, f"解析失败：{e}")
            except Exception:
                pass


def _tok(text: str) -> str:
    from utils.kb.tokenizer import tokenize_join
    return tokenize_join(text)


async def recover_interrupted():
    """服务重启兜底：把停留在「解析中」的文档置为失败（任务已随进程丢失）。"""
    try:
        from mybatisPlus import kb_orm
        ids = await kb_orm.get_running_doc_ids()
        for doc_id in ids:
            await kb_orm.set_document_parse_state(
                doc_id, -1, -1, "服务重启导致解析中断，请重新解析")
        if ids:
            kb_logger.info(f"kb 启动恢复：{len(ids)} 个中断的解析任务已置失败")
    except Exception as e:
        kb_logger.error(f"kb 启动恢复检查失败: {e}")
