# -*- coding：utf-8 -*-
"""文档解析后台任务：MinIO 取文件 → 抽文本 → 分块 → 向量化 → ES 写入 → 计数回写。

全部在 FastAPI 进程内以 asyncio 任务执行（lifespan 起协程，无额外进程）：
  - CPU/同步 IO（pdf/docx 解析、分块）经 asyncio.to_thread 卸载
  - 网络 IO（embedding、ES、MinIO）本身异步
  - 全局信号量限制同时解析文档数，防 embedding/ES 被打爆
重解析语义：先删该文档旧 chunk 再全量写入（chunk 计数按新旧差值回写库级）。

取消解析：视图层 request_cancel() 置本次任务的取消标志（协作式）。解析中的
to_thread 线程不可强杀，故在视觉逐项/逐页、配图上传、向量化批次、ES 写入前
等检查点主动退出（解析线程内的 VLM 项在标志置位后不再发起新请求，在途的最
多 concurrency 个完成后丢弃）。取消后文档状态置失败（run=-1，消息「已取消解
析」），用户可直接重解析。
"""
import asyncio
import time

from utils.getLogs import kb_logger
from utils.kb import es_client, minio_client
from utils.kb.embedding import embed_texts
from utils.kb.parser import attach_image_ids, extract_text, photo_key, split_chunks
from utils.kb.es_client import kb_cfg
from utils.kb.vision import ParseCancelled

_sem: asyncio.Semaphore | None = None
_tasks: set = set()  # 持有任务引用防 GC
# doc_id -> 本次解析任务的取消标志盒。每次 parse_document 创建新盒并登记（覆盖
# 旧盒，避免「取消→立刻重解析」时新旧任务串扰）；旧任务线程读自己闭包里的盒，
# 不受覆盖影响。
_cancel_boxes: dict = {}


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


def request_cancel(doc_id: int) -> bool:
    """请求取消该文档的解析（视图层调用）。返回是否找到在跑的解析任务。

    调用方负责把 DB 状态置为失败；本函数只让解析任务在下一个检查点退出，
    防止其继续跑完并覆写状态/写 ES。"""
    box = _cancel_boxes.get(doc_id)
    if box is None:
        return False
    box["cancelled"] = True
    return True


def _check_cancelled(box: dict):
    """解析任务内部检查点：命中取消标志即抛 ParseCancelled 中止。"""
    if box["cancelled"]:
        raise ParseCancelled()


async def parse_document(doc_id: int):
    from mybatisPlus import kb_orm

    # 盒在等信号量之前登记：排队中（run=0）也能被取消
    box = {"cancelled": False}
    _cancel_boxes[doc_id] = box  # 覆盖旧盒：取消永远针对「当前在跑」的解析

    def _cancelled() -> bool:
        return box["cancelled"]

    try:
        async with _get_sem():
            _check_cancelled(box)
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
            await kb_orm.set_document_parse_state(doc_id, 1, 0.05, "读取文件…")
            data = await minio_client.get_object(doc["location"])

            await kb_orm.set_document_parse_state(doc_id, 1, 0.2, "解析文本…")
            text, v_images = await asyncio.to_thread(extract_text, data, doc["file_type"],
                                                     _vision_progress_cb(doc_id),
                                                     kb.get("vision_config"), _cancelled)
            _check_cancelled(box)
            chunks = await asyncio.to_thread(split_chunks, text, chunk_num_cfg, parser_id)
            # 照片原图传对象存储作为 chunk 配图（单张失败仅丢该图，不阻断解析）。
            # 每次解析换随机 salt：取图接口无鉴权（<img> 无法带头），靠不可猜
            # key 防遍历；旧图先按文档前缀清理，重解析不残留
            uploaded = set()
            if v_images:
                import secrets as _secrets
                salt = _secrets.token_hex(8)
                for img in v_images:
                    img["salt"] = salt
                await minio_client.remove_prefix(f"kb/{doc['kb_id']}/doc/{doc_id}/")
                for img in v_images:
                    _check_cancelled(box)
                    key = photo_key(doc["kb_id"], doc_id, img)
                    try:
                        await minio_client.put_object(
                            key, img["data"], f"image/{img.get('ext') or 'png'}")
                        uploaded.add(key)
                    except Exception as e:
                        kb_logger.info(f"kb 文档 #{doc_id} 配图上传失败({key}): {e}")
                kb_logger.info(f"kb 文档 #{doc_id} 配图入库 {len(uploaded)}/{len(v_images)}")
            chunks = attach_image_ids(chunks, doc["kb_id"], doc_id, v_images)
            # 上传失败的配图不写进 chunk，避免检索返回取不到的图
            chunks = [(c[0], c[1], c[2],
                       [k for k in (c[3] or []) if k in uploaded] or None)
                      for c in chunks]
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
                _check_cancelled(box)
                vectors.extend(await embed_texts(texts[i:i + step], embd_id))
                prog = 0.3 + 0.6 * min(1.0, (i + step) / len(texts))
                await kb_orm.set_document_parse_state(doc_id, 1, round(prog, 2),
                                                      f"向量化 {min(i + step, len(texts))}/{len(texts)}")

            _check_cancelled(box)
            await kb_orm.set_document_parse_state(doc_id, 1, 0.95, "写入索引…")
            now = time.time()
            docs = [{
                "kb_id": doc["kb_id"], "doc_id": doc_id, "docnm": doc["name"],
                "content": c[0], "tokens": _tok(c[0]), "vec": v,
                "token_num": c[1], "position": c[2],                 "create_time_flt": now,
                "img_id": c[3] or [],
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
    except ParseCancelled:
        # 用户取消（取消接口已把状态置为失败「已取消解析」，这里不再写库，
        # 避免「取消后立即重解析」时旧任务覆写新任务状态）。不写 ES，直接结束；
        # 本次解析盒由 finally 统一清理。
        kb_logger.info(f"kb 文档 #{doc_id} 解析已取消")
        return
    except Exception as e:
        kb_logger.error(f"kb 文档 #{doc_id} 解析失败: {e}")
        try:
            await kb_orm.set_document_parse_state(doc_id, -1, -1, f"解析失败：{e}")
        except Exception:
            pass
    finally:
        # 清盒仅当仍是本次的盒（取消后立即重解析时，dict 里已是新盒，不误删）
        if _cancel_boxes.get(doc_id) is box:
            _cancel_boxes.pop(doc_id, None)


def _vision_progress_cb(doc_id: int):
    """视觉解析进度回调（在工作线程中被调用，仅 PDF+视觉开启时有意义）。

    用 run_coroutine_threadsafe 把进度写回主事件循环（0.2~0.3 段按页线性），
    回调自身节流交由 vision 侧控制，这里再加异常兜底保证不影响解析。
    """
    main_loop = asyncio.get_running_loop()

    def cb(done: int, total: int):
        if total <= 0:
            return
        prog = round(0.2 + 0.1 * min(1.0, done / total), 3)
        msg = f"视觉识别 {done}/{total}…"
        try:
            asyncio.run_coroutine_threadsafe(
                kb_orm_set_state(doc_id, prog, msg), main_loop)
        except Exception:
            pass

    return cb


async def kb_orm_set_state(doc_id: int, prog: float, msg: str):
    from mybatisPlus import kb_orm
    try:
        await kb_orm.set_document_parse_state(doc_id, 1, prog, msg)
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
