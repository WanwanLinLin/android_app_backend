# -*- coding：utf-8 -*-
"""KbDataset 加 rerank_limit 列（幂等：查 information_schema 后 ALTER）。

rerank_limit = 检索命中候选上限（融合截断/rerank 条数，8~256，默认 64）。

用法（本地开发库，连接取自 config.yaml）：
    /home/linwan/miniconda3/envs/android-backend/bin/python3 scripts/add_kb_rerank_limit.py
线上库执行需用户明确授权（线上连接需另行指向 IndustrialPark）。
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mybatisPlus.tables.sqlcli import async_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

DDL = ("ALTER TABLE KbDataset ADD COLUMN rerank_limit INT NULL "
       "COMMENT '检索候选命中上限（融合截断/rerank 条数，8~256）' "
       "AFTER similarity_threshold")


async def main():
    async with async_engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'KbDataset' AND COLUMN_NAME = 'rerank_limit'"
        ))).scalar()
        if row:
            print("rerank_limit 列已存在，无需操作")
            return
        await conn.execute(text(DDL))
        print("已添加 KbDataset.rerank_limit")


if __name__ == "__main__":
    asyncio.run(main())
