# -*- coding：utf-8 -*-
import sys
from pathlib import Path

FILE = Path(__file__).resolve()
ROOT = FILE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from setting import get_service

# 存储
ASYNC_SQLALCHEMY_DATABASE_URL = get_service("mysql")["async_url"]

# 异步操作
async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    pool_recycle=3600 * 2,
    echo=False,  # 打印SQL语句，开发时可用，生产环境关闭
    future=True  # 使用SQLAlchemy 2.0的新特性
)

# 4. 创建异步会话工厂（替代同步的sessionmaker）
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,  # 指定使用异步会话
    autoflush=False,  # 关闭自动刷新
    autocommit=False,  # 关闭自动提交
    expire_on_commit=False  # 提交后不失效对象，异步操作中建议设置
)

Base = declarative_base()
