# -*- coding: utf-8 -*-
import os
import time
import uuid

from . import schema
from typing import Union
from fastapi import APIRouter, UploadFile, File, Query, status, Depends

from utils.common.schema import GeneticResponse
from utils.admin_auth import current_admin, is_admin
from utils.getLogs import kb_logger
from mybatisPlus import kb_orm
from utils.kb import es_client, minio_client
from utils.kb.embedding import get_model_conf
from utils.kb.es_client import kb_cfg
from utils.kb.parser import SUPPORTED_EXTS, PARSER_METHODS, DEFAULT_PARSER
from utils.api_key_auth import current_api_key
from utils.kb.retrieval import retrieval
from utils.kb.tasks import spawn_parse

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})

# 自研知识库（对齐 ragflow 知识库能力）：MySQL 元数据 + ES 混合索引 + MinIO 源文件。
# 归属口径（沿用个性插件惯例）：每个登录账号可建自己的库并管理（建/改/删/上传/解析
# 仅创建者本人）；列表与读取 admin 可见全部（便于总览，展示归属），但不代管他人库。

_NOT_OWNER = GeneticResponse(code=403, msg="没有该知识库的访问权限（库归创建者私有）")


def _can_manage(admin: dict, kb: dict) -> bool:
    """管理权限：仅创建者本人；admin 也不代改代删别人的库。"""
    return bool(kb) and kb.get("created_by") == admin.get("id")


def _can_read(admin: dict, kb: dict) -> bool:
    """读取权限：创建者本人或 admin。"""
    return bool(kb) and (_can_manage(admin, kb) or is_admin(admin))


@router.get("/v1/kb/embeddingModels", summary="可用嵌入模型", tags=["通用接口"])
async def _embedding_models(admin: dict = Depends(current_admin)):
    emb = kb_cfg()["embedding"]
    models = [{"id": k, "dim": v.get("dim"), "default": k == emb["default"]}
              for k, v in (emb.get("models") or {}).items()]
    return GeneticResponse(data={"default": emb["default"], "models": models})


@router.get("/v1/kb/parserMethods", summary="可用切片方法（对齐 ragflow parser_id）", tags=["通用接口"])
async def _parser_methods(admin: dict = Depends(current_admin)):
    return GeneticResponse(data={"default": DEFAULT_PARSER,
                                 "methods": [{"id": k, "desc": v}
                                             for k, v in PARSER_METHODS.items()]})


# ---------------- 知识库 ----------------

@router.get("/v1/kb/list", summary="知识库列表", tags=["通用接口"])
async def _kb_list(admin: dict = Depends(current_admin)):
    return GeneticResponse(data=await kb_orm.list_datasets(
        admin_id=admin["id"], is_admin=is_admin(admin)))


@router.post("/v1/kb/add", summary="创建知识库", tags=["通用接口"])
async def _kb_add(info: schema.AddKbModel, admin: dict = Depends(current_admin)):
    try:
        conf = get_model_conf(info.embd_id)
    except ValueError as e:
        return GeneticResponse(code=400, msg=str(e))
    dim = int(conf.get("dim") or 1024)
    # 建库即确保该维度索引存在（失败不阻断，首次写入还会再建）
    try:
        await es_client.ensure_index(dim)
    except Exception as e:
        kb_logger.info(f"kb 预建索引失败（dim={dim}），首次写入时会自动重建: {e}")
    return await kb_orm.create_dataset(
        user_id=admin["id"], owner_name=admin.get("username"),
        name=info.name.strip(), desc=info.desc,
        embd_id=info.embd_id or kb_cfg()["embedding"]["default"], embd_dim=dim,
        chunk_token_num=info.chunk_token_num or 256,
        similarity_threshold=info.similarity_threshold if info.similarity_threshold is not None else 0.2,
        vector_similarity_weight=info.vector_similarity_weight if info.vector_similarity_weight is not None else 0.3,
        parser_id=info.parser_id if info.parser_id in PARSER_METHODS else DEFAULT_PARSER)


@router.get("/v1/kb/get/{kb_id}", summary="知识库详情", tags=["通用接口"])
async def _kb_get(kb_id: int, admin: dict = Depends(current_admin)):
    data = await kb_orm.get_dataset(kb_id)
    if not data:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_read(admin, data):
        return _NOT_OWNER
    return GeneticResponse(data=data)


@router.post("/v1/kb/update/{kb_id}", summary="更新知识库", tags=["通用接口"])
async def _kb_update(kb_id: int, info: schema.UpdateKbModel,
                     admin: dict = Depends(current_admin)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    payload = info.model_dump(exclude_none=True)
    if payload.get("parser_id") and payload["parser_id"] not in PARSER_METHODS:
        return GeneticResponse(code=400, msg="不支持的切片方法")
    return await kb_orm.update_dataset(kb_id, owner_id=admin["id"],
                                       is_admin=is_admin(admin),
                                       **payload)


@router.post("/v1/kb/delete/{kb_id}", summary="删除知识库（级联清 ES/MinIO）", tags=["通用接口"])
async def _kb_delete(kb_id: int, admin: dict = Depends(current_admin)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    if await kb_orm.get_running_doc_ids(kb_id):
        return GeneticResponse(code=400, msg="该知识库有文档正在解析中，请稍后再删")
    dim = kb["embd_dim"]
    docs = await kb_orm.list_documents(kb_id, 1, 100000)
    for d in docs["rows"]:
        try:
            await es_client.delete_by_doc(d["id"], dim)
        except Exception as e:
            kb_logger.error(f"kb 删库时清理文档 #{d['id']} ES 失败: {e}")
        if d.get("location"):
            try:
                await minio_client.remove_object(d["location"])
            except Exception as e:
                kb_logger.error(f"kb 删库时清理文档 #{d['id']} MinIO 失败: {e}")
    await kb_orm.soft_delete_dataset(kb_id)
    return GeneticResponse()


# ---------------- 文档 ----------------

@router.post("/v1/kb/{kb_id}/document/upload", summary="上传文档（可多选）", tags=["通用接口"])
async def _doc_upload(kb_id: int, files: list[UploadFile] = File(...),
                      parser_id: Union[str, None] = Query(None),
                      admin: dict = Depends(current_admin)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    # 上传可指定切片方法；不传/非法则继承知识库默认
    pid = parser_id if parser_id in PARSER_METHODS else (kb.get("parser_id") or DEFAULT_PARSER)
    uploaded, failed = [], []
    for f in files:
        name = os.path.basename(f.filename or "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in SUPPORTED_EXTS:
            failed.append(f"{name}：不支持的类型（{'/'.join(sorted(SUPPORTED_EXTS))}）")
            continue
        data = await f.read()
        if not data:
            failed.append(f"{name}：空文件")
            continue
        key = f"kb_{kb_id}/{uuid.uuid4().hex}.{ext}"
        try:
            await minio_client.put_object(key, data)
            doc = await kb_orm.create_document(kb_id, name, ext, len(data), key,
                                               parser_id=pid)
            spawn_parse(doc["id"])
            uploaded.append(doc)
        except Exception as e:
            failed.append(f"{name}：{e}")
    if not uploaded and failed:
        return GeneticResponse(code=500, msg="；".join(failed))
    return GeneticResponse(data={"uploaded": uploaded, "failed": failed})


@router.get("/v1/kb/{kb_id}/document/list", summary="文档列表（含解析进度）", tags=["通用接口"])
async def _doc_list(kb_id: int, page: int = 1, size: int = 20,
                    admin: dict = Depends(current_admin)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_read(admin, kb):
        return _NOT_OWNER
    return GeneticResponse(data=await kb_orm.list_documents(kb_id, page, size))


@router.post("/v1/kb/document/parse/{doc_id}", summary="解析/重新解析文档", tags=["通用接口"])
async def _doc_parse(doc_id: int, admin: dict = Depends(current_admin)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    if doc["run"] == 1:
        return GeneticResponse(code=400, msg="该文档正在解析中")
    await kb_orm.set_document_parse_state(doc_id, 0, 0.0, "排队中…")
    spawn_parse(doc_id)
    return GeneticResponse()


@router.post("/v1/kb/document/parser/{doc_id}", summary="修改文档切片方法（需重解析生效）", tags=["通用接口"])
async def _doc_parser(doc_id: int, info: schema.DocParserModel,
                      admin: dict = Depends(current_admin)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    if doc["run"] == 1:
        return GeneticResponse(code=400, msg="该文档正在解析中")
    if info.parser_id not in PARSER_METHODS:
        return GeneticResponse(code=400, msg="不支持的切片方法")
    return await kb_orm.set_document_parser(doc_id, info.parser_id)


@router.post("/v1/kb/document/available/{doc_id}", summary="启用/停用文档（停用后不参与检索）", tags=["通用接口"])
async def _doc_available(doc_id: int, info: schema.DocAvailableModel,
                         admin: dict = Depends(current_admin)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    r = await kb_orm.set_document_available(doc_id, bool(info.available))
    if r.code != 200:
        return r
    # 同步 ES：把它全部 chunk 的 available_int 改掉（检索层据此过滤）。失败回滚 MySQL 标志
    try:
        await es_client.set_doc_available(doc_id, bool(info.available))
    except Exception as e:
        kb_logger.error(f"kb 文档 #{doc_id} 切换可用状态同步 ES 失败: {e}")
        await kb_orm.set_document_available(doc_id, not bool(info.available))
        return GeneticResponse(code=500, msg="切换失败：索引更新异常，已回滚")
    return r


@router.post("/v1/kb/document/delete/{doc_id}", summary="删除文档（清 ES/MinIO）", tags=["通用接口"])
async def _doc_delete(doc_id: int, admin: dict = Depends(current_admin)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    if doc["run"] == 1:
        return GeneticResponse(code=400, msg="文档正在解析中，请稍后再删")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(admin, kb):
        return _NOT_OWNER
    try:
        await es_client.delete_by_doc(doc_id, kb["embd_dim"])
    except Exception as e:
        kb_logger.error(f"kb 删除文档 #{doc_id} ES 清理失败: {e}")
    if doc.get("location"):
        try:
            await minio_client.remove_object(doc["location"])
        except Exception as e:
            kb_logger.error(f"kb 删除文档 #{doc_id} MinIO 清理失败: {e}")
    await kb_orm.soft_delete_document(doc_id)
    return GeneticResponse()


@router.get("/v1/kb/{kb_id}/chunk/list", summary="文档 chunk 列表", tags=["通用接口"])
async def _chunk_list(kb_id: int, doc_id: int, page: int = 1, size: int = 20,
                      admin: dict = Depends(current_admin)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_read(admin, kb):
        return _NOT_OWNER
    return GeneticResponse(data=await es_client.list_chunks_by_doc(doc_id, kb["embd_dim"], page, size))


# ---------------- 检索 ----------------

@router.post("/v1/kb/retrieval", summary="知识库检索测试", tags=["通用接口"])
async def _retrieval(info: schema.KbRetrievalModel, admin: dict = Depends(current_admin)):
    if not info.kb_ids:
        return GeneticResponse(code=400, msg="请选择知识库")
    kb_metas = []
    for kb_id in info.kb_ids:
        kb = await kb_orm.get_dataset(kb_id)
        if not kb:
            return GeneticResponse(code=400, msg=f"知识库 #{kb_id} 不存在")
        if not _can_read(admin, kb):
            return _NOT_OWNER
        kb_metas.append({"kb_id": kb_id, "dim": kb["embd_dim"],
                         "vsw": kb["vector_similarity_weight"]})
    dims = {m["dim"] for m in kb_metas}
    if len(dims) > 1:
        return GeneticResponse(code=400, msg="所选知识库向量维度不一致，无法联合检索")
    start = time.perf_counter()
    try:
        data = await retrieval(
            info.question, kb_metas, page=info.page or 1, size=info.size or 10,
            similarity_threshold=info.similarity_threshold,
            vector_similarity_weight=info.vector_similarity_weight)
    except Exception as e:
        kb_logger.error(f"kb 检索失败: {e}")
        return GeneticResponse(code=500, msg=f"检索失败：{e}")
    data["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
    return GeneticResponse(data=data)


# ---------------- 对外接口（Bearer API Key 鉴权） ----------------
# API Key 为账号级凭证（管理接口在 /v1/user/apikey/*，见 modules/user/views.py），
# 本模块只是消费方：以 key 归属用户身份复用 _can_manage/_can_read（二者只比
# created_by），可访问且仅可访问其自建知识库；admin 也不扩大 key 的可见范围。

def _actor_of(key: dict) -> dict:
    return {"id": key["created_by"], "role": "user", "username": key.get("owner_name")}


async def _owner_kb_metas(key: dict, kb_ids=None):
    """key 可检索的库：传 kb_ids 则逐个校验归属，否则取归属者全部库。返回 (metas, err)。"""
    actor = _actor_of(key)
    if kb_ids:
        metas = []
        for kb_id in kb_ids:
            kb = await kb_orm.get_dataset(kb_id)
            if not kb:
                return None, GeneticResponse(code=400, msg=f"知识库 #{kb_id} 不存在")
            if not _can_manage(actor, kb):  # 对外严格：只认归属者本人，不含 admin 放宽
                return None, GeneticResponse(code=403, msg=f"知识库 #{kb_id} 不属于该 API Key")
            metas.append({"kb_id": kb_id, "dim": kb["embd_dim"],
                          "vsw": kb["vector_similarity_weight"]})
        return metas, None
    ds = await kb_orm.list_datasets(admin_id=key["created_by"], is_admin=False)
    metas = [{"kb_id": d["id"], "dim": d["embd_dim"],
              "vsw": d["vector_similarity_weight"]} for d in ds["rows"]]
    return metas, None


@router.get("/v1/kb/open/kb/list", summary="[Open] 该 Key 可见的知识库列表", tags=["对外接口"])
async def _open_kb_list(key: dict = Depends(current_api_key)):
    ds = await kb_orm.list_datasets(admin_id=key["created_by"], is_admin=False)
    rows = [{"id": d["id"], "name": d["name"], "desc": d["desc"],
             "doc_num": d["doc_num"], "chunk_num": d["chunk_num"],
             "embd_dim": d["embd_dim"], "parser_id": d["parser_id"],
             "create_time": d["create_time"]} for d in ds["rows"]]
    return GeneticResponse(data={"rows": rows, "total": len(rows)})


@router.post("/v1/kb/open/retrieval", summary="[Open] 知识库检索", tags=["对外接口"])
async def _open_retrieval(info: schema.OpenRetrievalModel,
                          key: dict = Depends(current_api_key)):
    metas, err = await _owner_kb_metas(key, info.kb_ids)
    if err:
        return err
    if not metas:
        return GeneticResponse(data={"chunks": [], "total": 0, "elapsed_ms": 0})
    dims = {m["dim"] for m in metas}
    if len(dims) > 1:
        return GeneticResponse(code=400, msg="该 Key 下知识库向量维度不一致，请用 kb_ids 指定单库检索")
    start = time.perf_counter()
    try:
        data = await retrieval(
            info.question, metas, page=info.page or 1, size=info.size or 10,
            similarity_threshold=info.similarity_threshold,
            vector_similarity_weight=info.vector_similarity_weight)
    except Exception as e:
        kb_logger.error(f"kb[open] 检索失败: {e}")
        return GeneticResponse(code=500, msg=f"检索失败：{e}")
    data["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
    return GeneticResponse(data=data)


@router.get("/v1/kb/open/{kb_id}/document/list", summary="[Open] 文档列表", tags=["对外接口"])
async def _open_doc_list(kb_id: int, page: int = 1, size: int = 20,
                         key: dict = Depends(current_api_key)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(_actor_of(key), kb):
        return _NOT_OWNER
    return GeneticResponse(data=await kb_orm.list_documents(kb_id, page, size))


@router.get("/v1/kb/open/{kb_id}/chunk/list", summary="[Open] 文档 chunk 列表", tags=["对外接口"])
async def _open_chunk_list(kb_id: int, doc_id: int, page: int = 1, size: int = 20,
                           key: dict = Depends(current_api_key)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(_actor_of(key), kb):
        return _NOT_OWNER
    return GeneticResponse(data=await es_client.list_chunks_by_doc(doc_id, kb["embd_dim"], page, size))


@router.post("/v1/kb/open/{kb_id}/document/upload", summary="[Open] 上传文档", tags=["对外接口"])
async def _open_doc_upload(kb_id: int, files: list[UploadFile] = File(...),
                           parser_id: Union[str, None] = Query(None),
                           key: dict = Depends(current_api_key)):
    kb = await kb_orm.get_dataset(kb_id)
    if not kb:
        return GeneticResponse(code=400, msg="知识库不存在")
    if not _can_manage(_actor_of(key), kb):
        return _NOT_OWNER
    pid = parser_id if parser_id in PARSER_METHODS else (kb.get("parser_id") or DEFAULT_PARSER)
    uploaded, failed = [], []
    for f in files:
        name = os.path.basename(f.filename or "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in SUPPORTED_EXTS:
            failed.append(f"{name}：不支持的类型（{'/'.join(sorted(SUPPORTED_EXTS))}）")
            continue
        data = await f.read()
        if not data:
            failed.append(f"{name}：空文件")
            continue
        obj_key = f"kb_{kb_id}/{uuid.uuid4().hex}.{ext}"
        try:
            await minio_client.put_object(obj_key, data)
            doc = await kb_orm.create_document(kb_id, name, ext, len(data), obj_key, parser_id=pid)
            spawn_parse(doc["id"])
            uploaded.append(doc)
        except Exception as e:
            failed.append(f"{name}：{e}")
    if not uploaded and failed:
        return GeneticResponse(code=500, msg="；".join(failed))
    return GeneticResponse(data={"uploaded": uploaded, "failed": failed})


@router.post("/v1/kb/open/document/parse/{doc_id}", summary="[Open] 解析/重解析文档", tags=["对外接口"])
async def _open_doc_parse(doc_id: int, key: dict = Depends(current_api_key)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(_actor_of(key), kb):
        return _NOT_OWNER
    if doc["run"] == 1:
        return GeneticResponse(code=400, msg="该文档正在解析中")
    await kb_orm.set_document_parse_state(doc_id, 0, 0.0, "排队中…")
    spawn_parse(doc_id)
    return GeneticResponse()


@router.post("/v1/kb/open/document/delete/{doc_id}", summary="[Open] 删除文档", tags=["对外接口"])
async def _open_doc_delete(doc_id: int, key: dict = Depends(current_api_key)):
    doc = await kb_orm.get_document(doc_id)
    if not doc:
        return GeneticResponse(code=400, msg="文档不存在")
    if doc["run"] == 1:
        return GeneticResponse(code=400, msg="文档正在解析中，请稍后再删")
    kb = await kb_orm.get_dataset(doc["kb_id"])
    if not _can_manage(_actor_of(key), kb):
        return _NOT_OWNER
    try:
        await es_client.delete_by_doc(doc_id, kb["embd_dim"])
    except Exception as e:
        kb_logger.error(f"kb[open] 删除文档 #{doc_id} ES 清理失败: {e}")
    if doc.get("location"):
        try:
            await minio_client.remove_object(doc["location"])
        except Exception as e:
            kb_logger.error(f"kb[open] 删除文档 #{doc_id} MinIO 清理失败: {e}")
    await kb_orm.soft_delete_document(doc_id)
    return GeneticResponse()
