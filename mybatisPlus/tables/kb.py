# -*- coding：utf-8 -*-
from .sqlcli import Base
# 本项目不使用数据库外键约束：请勿在此引入 ForeignKey / create_foreign_key，
# 表间引用完整性一律由应用层校验保证。
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT

from .industrial_park import beijing_now


# 知识库模块（自研，功能对齐 RAGFlow 知识库）：
#   MySQL 只存元数据与计数，chunk 正文/向量全部在 ES（索引 kb_chunk_{维}，按租户
#   场景全局共享一个索引，库间靠 kb_id 过滤，与 ragflow 的租户级索引同思路），
#   原始文件在 MinIO（bucket=kb）。解析走 asyncio 后台任务，进度回写 Document。


class KbDataset(Base):
    """知识库表（对应 ragflow 的 Knowledgebase）。"""
    __tablename__ = "KbDataset"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), index=True, nullable=False, comment="知识库名称")
    desc = Column(String(512), default=None, comment="描述")
    created_by = Column(Integer, index=True, default=None, comment="创建者 User.id（无外键）；库归创建者私有，admin 不代改代删")
    owner_name = Column(String(64), default=None, comment="创建者用户名（冗余，admin 列表展示归属）")
    embd_id = Column(String(128), default=None, comment="嵌入模型名（config.yaml kb.embedding.models 的键）")
    embd_dim = Column(Integer, default=1024, comment="向量维度（建库后不可变更，ES 向量列按维分列）")
    parser_id = Column(String(32), default="General", comment="默认切片方法（对齐 ragflow parser_id），文档未单独指定时继承")
    chunk_token_num = Column(Integer, default=256, comment="分块目标 token 数")
    similarity_threshold = Column(Float, default=0.2, comment="检索相似度阈值")
    vector_similarity_weight = Column(Float, default=0.3, comment="融合打分中向量分量权重（其余为全文 BM25 归一权重）")
    doc_num = Column(Integer, default=0, comment="文档数（冗余计数）")
    chunk_num = Column(Integer, default=0, comment="chunk 数（冗余计数）")
    token_num = Column(Integer, default=0, comment="token 总数（冗余计数）")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")


class KbDocument(Base):
    """知识库文档表（对应 ragflow 的 Document）。"""
    __tablename__ = "KbDocument"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, index=True, nullable=False, comment="所属知识库id（KbDataset.id，无外键）")
    name = Column(String(256), nullable=False, comment="文件名")
    file_type = Column(String(32), default=None, comment="扩展名：txt|md|pdf|docx")
    size = Column(Integer, default=0, comment="文件字节数")
    location = Column(String(512), default=None, comment="MinIO 对象 key")
    # 状态机与 ragflow Document.run/progress 对齐：0 未解析 / 1 解析中 / 2 已取消 / 3 完成 / -1 失败
    run = Column(Integer, index=True, default=0, comment="0未解析|1解析中|2取消|3完成|-1失败")
    progress = Column(Float, default=0.0, comment="解析进度 0~1（失败时为 -1）")
    progress_msg = Column(Text, default=None, comment="解析过程/错误信息")
    parser_id = Column(String(32), default=None, comment="切片方法（对齐 ragflow parser_id）：General|Q&A|Manual|Paper|Book|Laws|One|Tag，缺省 General")
    parser_config = Column(JSON, default=None, comment="文档级解析参数（chunk_token_num 覆盖库级）")
    available = Column(Boolean, default=True, comment="是否启用（停用后其 chunk 在 ES 置 available_int=0，不参与检索）")
    chunk_num = Column(Integer, default=0, comment="chunk 数")
    token_num = Column(Integer, default=0, comment="token 数")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
