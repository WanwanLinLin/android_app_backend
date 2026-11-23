# -*- coding：utf-8 -*-
"""知识库模块建表脚本（幂等，仅创建 KbDataset / KbDocument 两张新表）。

用法（本地开发库）：
    /home/linwan/miniconda3/envs/android-backend/bin/python3 scripts/init_kb_tables.py
线上库执行需明确授权，并把 config.yaml 指向线上后再跑。
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mybatisPlus.tables.sqlcli import async_engine  # noqa: E402
from mybatisPlus.tables.kb import KbDataset, KbDocument  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


async def main():
    # 仅建这两张表，不触碰其余表（create_all 默认 checkfirst=True，存在即跳过）
    async with async_engine.begin() as conn:
        def _create(sync_conn):
            existing = set(inspect(sync_conn).get_table_names())
            created = []
            for model in (KbDataset, KbDocument):
                if model.__tablename__ not in existing:
                    model.__table__.create(sync_conn)
                    created.append(model.__tablename__)
            return created
        created = await conn.run_sync(_create)
    print("已创建表:", created or "（均已存在，无需操作）")


if __name__ == "__main__":
    asyncio.run(main())
