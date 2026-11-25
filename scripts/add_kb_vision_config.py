# -*- coding：utf-8 -*-
"""KbDataset 加 vision_config 列（幂等：查 information_schema 后 ALTER）。

vision_config = PDF 图像分析的库级覆盖（JSON：{page_ocr: all|scan|off,
photo_describe: bool}），缺省 NULL 表示完全跟随 config.yaml kb.vision。

用法（本地开发库，连接取自 config.yaml）：
    /home/linwan/miniconda3/envs/android-backend/bin/python3 scripts/add_kb_vision_config.py
线上库执行需用户明确授权（线上连接需另行指向 IndustrialPark）。
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mybatisPlus.tables.sqlcli import async_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

DDL = ("ALTER TABLE KbDataset ADD COLUMN vision_config JSON NULL "
       "COMMENT 'PDF 图像分析库级覆盖：{page_ocr: all|scan|off, photo_describe: bool}，缺省跟随 config kb.vision' "
       "AFTER rerank_limit")


async def main():
    async with async_engine.begin() as conn:
        row = (await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'KbDataset' AND COLUMN_NAME = 'vision_config'"
        ))).scalar()
        if row:
            print("vision_config 列已存在，无需操作")
            return
        await conn.execute(text(DDL))
        print("已添加 KbDataset.vision_config")


if __name__ == "__main__":
    asyncio.run(main())
