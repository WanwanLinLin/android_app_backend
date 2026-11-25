# -*- coding：utf-8 -*-
"""MinIO 对象存储异步封装。

基于 miniopy-async（minio SDK 的 aiohttp 异步移植版，API 与官方同步 SDK 对齐），
所有调用原生 await，不经过线程池，对 FastAPI 事件循环零阻塞。
客户端内部复用一个 aiohttp ClientSession，进程退出时通过 close_client() 释放。
"""
import asyncio
import io

from miniopy_async import Minio

from setting import get_service
from utils.kb.es_client import kb_cfg

_client: Minio | None = None
_bucket_ready = False
_lock = asyncio.Lock()


def _build() -> Minio:
    cfg = kb_cfg()
    return Minio(cfg["minio_endpoint"],
                 access_key=cfg["minio_access_key"],
                 secret_key=cfg["minio_secret_key"],
                 secure=cfg.get("minio_secure", False))


async def _ensure_bucket():
    global _client, _bucket_ready
    if _client is None:
        _client = _build()
    if _bucket_ready:
        return
    async with _lock:
        if _bucket_ready:
            return
        bucket = kb_cfg()["minio_bucket"]
        if not await _client.bucket_exists(bucket):
            await _client.make_bucket(bucket)
        _bucket_ready = True


async def put_object(key: str, data: bytes, content_type: str = "application/octet-stream"):
    await _ensure_bucket()
    bucket = kb_cfg()["minio_bucket"]
    await _client.put_object(bucket, key, io.BytesIO(data), len(data),
                             content_type=content_type)


async def get_object(key: str) -> bytes:
    await _ensure_bucket()
    bucket = kb_cfg()["minio_bucket"]
    resp = await _client.get_object(bucket, key)
    try:
        return await resp.read()
    finally:
        resp.release()


async def remove_object(key: str):
    await _ensure_bucket()
    bucket = kb_cfg()["minio_bucket"]
    await _client.remove_object(bucket, key)


async def remove_prefix(prefix: str) -> int:
    """删除前缀下全部对象（文档重解析/删除时清配图）。返回删除数，单项失败不中断。"""
    await _ensure_bucket()
    bucket = kb_cfg()["minio_bucket"]
    n = 0
    try:
        objs = await _client.list_objects(bucket, prefix=prefix, recursive=True)
    except Exception:
        return 0
    for obj in objs:
        try:
            await _client.remove_object(bucket, obj.object_name)
            n += 1
        except Exception:
            pass
    return n


async def presigned_get_object(key: str, expires_seconds: int = 3600) -> str:
    """生成临时下载链接（前端直读源文件时用，可选能力）。"""
    await _ensure_bucket()
    from datetime import timedelta
    bucket = kb_cfg()["minio_bucket"]
    return await _client.presigned_get_object(bucket, key,
                                              expires=timedelta(seconds=expires_seconds))


async def close_client():
    """应用关闭时释放 aiohttp 会话。"""
    global _client, _bucket_ready
    if _client is not None:
        await _client.close_session()
        _client = None
        _bucket_ready = False
