# -*- coding：utf-8 -*-
"""知识库模块数据访问层（KbDataset / KbDocument）。

约定与其余 *_orm 一致：全部 async、返回 dict 或 GeneticResponse；
is_delete 历史可能为 NULL，过滤一律 COALESCE；不使用数据库外键。
chunk 不在 MySQL，检索与正文存取全部走 ES（utils/kb/es_client.py）。
API Key 是账号级凭证，已迁至 api_key_orm（UserApiKey）。
"""
from sqlalchemy import func, select, update

from .tables.sqlcli import AsyncSessionLocal
from .tables.kb import KbDataset, KbDocument
from utils.common.schema import GeneticResponse


def _alive(m):
    return (m.is_delete.is_(None)) | (m.is_delete.is_(False))


def _ser_dataset(d: KbDataset) -> dict:
    return {"id": d.id, "name": d.name, "desc": d.desc, "created_by": d.created_by,
            "owner_name": d.owner_name,
            "embd_id": d.embd_id, "embd_dim": d.embd_dim,
            "parser_id": d.parser_id or "General",
            "chunk_token_num": d.chunk_token_num,
            "similarity_threshold": d.similarity_threshold,
            "vector_similarity_weight": d.vector_similarity_weight,
            "doc_num": d.doc_num or 0, "chunk_num": d.chunk_num or 0,
            "token_num": d.token_num or 0,
            "create_time": d.create_time.strftime("%Y-%m-%d %H:%M:%S") if d.create_time else None,
            "update_time": d.update_time.strftime("%Y-%m-%d %H:%M:%S") if d.update_time else None}


def _ser_document(c: KbDocument) -> dict:
    return {"id": c.id, "kb_id": c.kb_id, "name": c.name, "file_type": c.file_type,
            "size": c.size or 0, "location": c.location,
            "run": c.run if c.run is not None else 0,
            "progress": c.progress if c.progress is not None else 0.0,
            "progress_msg": c.progress_msg,
            "parser_id": c.parser_id or "General",
            "parser_config": c.parser_config,
            "available": True if c.available is None else bool(c.available),
            "chunk_num": c.chunk_num or 0, "token_num": c.token_num or 0,
            "create_time": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else None,
            "update_time": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else None}


# ---------------- 知识库 ----------------

async def create_dataset(user_id: int, name: str, desc=None, embd_id=None,
                         embd_dim: int = 1024, chunk_token_num: int = 256,
                         similarity_threshold: float = 0.2,
                         vector_similarity_weight: float = 0.3,
                         parser_id: str = "General",
                         owner_name: str = None):
    async with AsyncSessionLocal() as session:
        # 库按创建者私有：同名查重仅限本人库内，不同用户可建同名库
        dup = await session.scalar(select(KbDataset).where(
            KbDataset.name == name, KbDataset.created_by == user_id, _alive(KbDataset)))
        if dup:
            return GeneticResponse(code=400, msg="你已创建过同名知识库")
        d = KbDataset(name=name, desc=desc, created_by=user_id, owner_name=owner_name,
                      embd_id=embd_id,
                      embd_dim=embd_dim, chunk_token_num=chunk_token_num,
                      similarity_threshold=similarity_threshold,
                      vector_similarity_weight=vector_similarity_weight,
                      parser_id=parser_id or "General")
        session.add(d)
        await session.commit()
        await session.refresh(d)
        return GeneticResponse(data=_ser_dataset(d))


async def list_datasets(admin_id: int = None, is_admin: bool = False):
    """普通用户只见自己创建的库；admin 可见全部（列表展示归属）。"""
    async with AsyncSessionLocal() as session:
        stmt = select(KbDataset).where(_alive(KbDataset))
        if not is_admin:
            stmt = stmt.where(KbDataset.created_by == admin_id)
        rows = (await session.scalars(
            stmt.order_by(KbDataset.id.desc())
        )).all()
        result = [_ser_dataset(d) for d in rows]
        return {"rows": result, "total": len(result)}


async def get_dataset(kb_id: int):
    async with AsyncSessionLocal() as session:
        d = await session.scalar(select(KbDataset).filter_by(id=kb_id))
        if not d or d.is_delete:
            return None
        return _ser_dataset(d)


async def update_dataset(kb_id: int, owner_id: int = None, is_admin: bool = False,
                         **payload):
    # embd_id/embd_dim 建库后不可改（换嵌入模型必须重解析全部文档，暂不开放）
    allowed = {k: v for k, v in payload.items()
               if k in ("name", "desc", "chunk_token_num", "parser_id",
                        "similarity_threshold", "vector_similarity_weight")
               and v is not None}
    if not allowed:
        return GeneticResponse(code=400, msg="没有可更新的字段")
    async with AsyncSessionLocal() as session:
        d = await session.scalar(select(KbDataset).filter_by(id=kb_id))
        if not d or d.is_delete:
            return GeneticResponse(code=400, msg="知识库不存在")
        if "name" in allowed:
            # 同名查重与建库口径一致：仅同一创建者库内互斥
            dup_stmt = select(KbDataset).where(
                KbDataset.name == allowed["name"], KbDataset.id != kb_id, _alive(KbDataset))
            if not is_admin:
                dup_stmt = dup_stmt.where(KbDataset.created_by == owner_id)
            else:
                dup_stmt = dup_stmt.where(KbDataset.created_by == d.created_by)
            dup = await session.scalar(dup_stmt)
            if dup:
                return GeneticResponse(code=400, msg="已存在同名知识库")
        for k, v in allowed.items():
            setattr(d, k, v)
        await session.commit()
        return GeneticResponse()


async def soft_delete_dataset(kb_id: int):
    """软删知识库行（ES/MinIO 清理由视图层的 delete_dataset_resources 完成）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(KbDataset).where(KbDataset.id == kb_id).values(is_delete=True))
        await session.execute(
            update(KbDocument).where(KbDocument.kb_id == kb_id).values(is_delete=True))
        await session.commit()


# ---------------- 文档 ----------------

async def create_document(kb_id: int, name: str, file_type: str, size: int, location: str,
                          parser_id: str = None, parser_config=None):
    async with AsyncSessionLocal() as session:
        c = KbDocument(kb_id=kb_id, name=name, file_type=file_type, size=size,
                       location=location, parser_id=parser_id, parser_config=parser_config)
        session.add(c)
        await session.execute(
            update(KbDataset).where(KbDataset.id == kb_id)
            .values(doc_num=func.coalesce(KbDataset.doc_num, 0) + 1))
        await session.commit()
        await session.refresh(c)
        return _ser_document(c)


async def list_documents(kb_id: int, page: int = 1, size: int = 20):
    async with AsyncSessionLocal() as session:
        total = await session.scalar(
            select(func.count()).select_from(KbDocument)
            .where(KbDocument.kb_id == kb_id, _alive(KbDocument))) or 0
        rows = (await session.scalars(
            select(KbDocument)
            .where(KbDocument.kb_id == kb_id, _alive(KbDocument))
            .order_by(KbDocument.id.desc()).offset((page - 1) * size).limit(size)
        )).all()
        return {"rows": [_ser_document(c) for c in rows], "total": total}


async def get_document(doc_id: int):
    async with AsyncSessionLocal() as session:
        c = await session.scalar(select(KbDocument).filter_by(id=doc_id))
        if not c or c.is_delete:
            return None
        return _ser_document(c)


async def set_document_parse_state(doc_id: int, run: int, progress: float = None,
                                   progress_msg: str = None):
    values = {"run": run}
    if progress is not None:
        values["progress"] = progress
    if progress_msg is not None:
        values["progress_msg"] = progress_msg[:2000] if progress_msg else progress_msg
    async with AsyncSessionLocal() as session:
        await session.execute(update(KbDocument).where(KbDocument.id == doc_id).values(**values))
        await session.commit()


async def set_document_parser(doc_id: int, parser_id: str):
    """修改文档的切片方法（切换后需重解析才生效）。"""
    async with AsyncSessionLocal() as session:
        c = await session.scalar(select(KbDocument).filter_by(id=doc_id))
        if not c or c.is_delete:
            return GeneticResponse(code=400, msg="文档不存在")
        await session.execute(update(KbDocument).where(KbDocument.id == doc_id)
                               .values(parser_id=parser_id))
        await session.commit()
        return GeneticResponse(data={"id": doc_id, "parser_id": parser_id})


async def set_document_available(doc_id: int, available: bool):
    async with AsyncSessionLocal() as session:
        c = await session.scalar(select(KbDocument).filter_by(id=doc_id))
        if not c or c.is_delete:
            return GeneticResponse(code=400, msg="文档不存在")
        await session.execute(update(KbDocument).where(KbDocument.id == doc_id)
                               .values(available=available))
        await session.commit()
        return GeneticResponse(data={"id": doc_id, "available": bool(available)})


async def finish_document(doc_id: int, kb_id: int, chunk_num: int, token_num: int):
    """解析完成：回写文档计数并原子增加库级计数（旧 chunk 已在解析前清理，直接置数）。"""
    async with AsyncSessionLocal() as session:
        old = await session.scalar(select(KbDocument).filter_by(id=doc_id))
        old_chunk = (old.chunk_num or 0) if old else 0
        old_token = (old.token_num or 0) if old else 0
        await session.execute(update(KbDocument).where(KbDocument.id == doc_id).values(
            run=3, progress=1.0, chunk_num=chunk_num, token_num=token_num))
        await session.execute(update(KbDataset).where(KbDataset.id == kb_id).values(
            chunk_num=func.coalesce(KbDataset.chunk_num, 0) + chunk_num - old_chunk,
            token_num=func.coalesce(KbDataset.token_num, 0) + token_num - old_token))
        await session.commit()


async def soft_delete_document(doc_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(KbDocument).where(KbDocument.id == doc_id).values(is_delete=True))
        await session.commit()


async def get_running_doc_ids(kb_id: int = None):
    """当前处于「解析中」的文档 id（删除文档/库前的并发检查）。"""
    async with AsyncSessionLocal() as session:
        stmt = select(KbDocument.id).where(_alive(KbDocument), KbDocument.run == 1)
        if kb_id:
            stmt = stmt.where(KbDocument.kb_id == kb_id)
        return set((await session.scalars(stmt)).all())
