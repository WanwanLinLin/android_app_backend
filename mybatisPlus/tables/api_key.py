# -*- coding：utf-8 -*-
from .sqlcli import Base
# 本项目不使用数据库外键约束：请勿在此引入 ForeignKey / create_foreign_key，
# 表间引用完整性一律由应用层校验保证。
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from .industrial_park import beijing_now


class UserApiKey(Base):
    """账号级对外 API Key（模块无关，供各模块开放接口共用鉴权）。

    管理接口 /v1/user/apikey/*（JWT）；消费方以 Bearer sk-xxx 调用各模块
    开放接口（当前：知识库 /v1/kb/open/*），后续新模块复用同一密钥与
    鉴权依赖（utils/api_key_auth.current_api_key）。
    安全口径：库里只存 SHA256 哈希，明文仅在创建响应里出现一次；
    key 归属某后台账号，开放接口以归属者身份判定数据范围。"""
    __tablename__ = "UserApiKey"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), default=None, comment="备注名（如“产线质检系统”）")
    key_hash = Column(String(64), unique=True, index=True, nullable=False, comment="API Key 的 SHA256 十六进制")
    key_prefix = Column(String(16), default=None, comment="明文前 11 位（列表展示辨认用，非机密）")
    created_by = Column(Integer, index=True, nullable=False, comment="归属 User.id（无外键）")
    owner_name = Column(String(64), default=None, comment="归属用户名（冗余展示）")
    status = Column(Integer, default=1, comment="1 启用 / 0 停用（停用即时失效，可恢复）")
    last_used_time = Column(DateTime, default=None, comment="最近一次调用时间")
    create_time = Column(DateTime, default=lambda: beijing_now())
    update_time = Column(DateTime, default=lambda: beijing_now(), onupdate=lambda: beijing_now())
    is_delete = Column(Boolean, index=True, default=False, comment="该条记录是否已被删除")
