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
from setting import config_data

# 存储
ASYNC_SQLALCHEMY_DATABASE_URL = config_data["SERVICES"][-2]["async_url"]

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


# ################## 独立连接工单系统 ################## 

ASYNC_SQLALCHEMY_DATABASE_URL_WORKORDER = config_data["SERVICES"][-2]["business_async_url"]

# 异步操作
work_order_async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    pool_recycle=3600 * 2,
    echo=False,  # 打印SQL语句，开发时可用，生产环境关闭
    future=True  # 使用SQLAlchemy 2.0的新特性
)

# 4. 创建异步会话工厂（替代同步的sessionmaker）
WorkOrderAsyncSessionLocal = async_sessionmaker(
    bind=work_order_async_engine,
    class_=AsyncSession,  # 指定使用异步会话
    autoflush=False,  # 关闭自动刷新
    autocommit=False,  # 关闭自动提交
    expire_on_commit=False  # 提交后不失效对象，异步操作中建议设置
)

Base_Work_Order = declarative_base()