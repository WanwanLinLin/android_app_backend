# -*- coding：utf-8 -*-
"""账号级 API Key 建表脚本（幂等，仅创建 UserApiKey 一张表）。

UserApiKey 为模块无关的账号级凭证表（原 KbApiKey 的替代，管理接口
/v1/user/apikey/*）。若存在旧表 KbApiKey（已废弃的 kb 专属设计，
仅存在于开发库），迁移未删除的行后改名备份，不直接 DROP。

用法（本地开发库）：
    /home/linwan/miniconda3/envs/android-backend/bin/python3 scripts/init_api_key_table.py
线上库执行需明确授权，并把 config.yaml 指向线上后再跑。
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402
from mybatisPlus.tables.sqlcli import async_engine  # noqa: E402
from mybatisPlus.tables.api_key import UserApiKey  # noqa: E402


async def main():
    async with async_engine.begin() as conn:
        def _create(sync_conn):
            insp = inspect(sync_conn)
            existing = set(insp.get_table_names())
            if UserApiKey.__tablename__ not in existing:
                UserApiKey.__table__.create(sync_conn)
                print("已创建 UserApiKey")
            else:
                print("UserApiKey 已存在，跳过")
            return existing
        existing = await conn.run_sync(_create)

        # 旧 kb 专属表迁移：未软删的行搬入新表，旧表改名备份（不 DROP）
        if "KbApiKey" in existing:
            rows = (await conn.execute(text(
                "SELECT id,name,key_hash,key_prefix,created_by,owner_name,status,"
                "COALESCE(last_used_time,NULL),create_time,update_time "
                "FROM KbApiKey WHERE COALESCE(is_delete,0)=0"))).fetchall()
            moved = 0
            for r in rows:
                dup = (await conn.execute(text(
                    "SELECT id FROM UserApiKey WHERE key_hash=:h"),
                    {"h": r[2]})).fetchone()
                if dup:
                    continue
                await conn.execute(text(
                    "INSERT INTO UserApiKey (id,name,key_hash,key_prefix,created_by,"
                    "owner_name,status,last_used_time,create_time,update_time,is_delete) "
                    "VALUES (:id,:name,:h,:p,:c,:o,1,:lu,:ct,:ut,0)"),
                    {"id": r[0], "name": r[1], "h": r[2], "p": r[3], "c": r[4],
                     "o": r[5], "lu": r[7], "ct": r[8], "ut": r[9]})
                moved += 1
            from datetime import datetime
            bak = "KbApiKey_bak_20261123"
            if (await conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t"),
                    {"t": bak})).scalar():
                bak = "KbApiKey_bak_" + datetime.now().strftime("%Y%m%d%H%M%S")
            await conn.execute(text(f"RENAME TABLE KbApiKey TO `{bak}`"))
            print(f"KbApiKey：迁移 {moved} 行有效数据 → 已备份为 {bak}")
        else:
            print("无旧表 KbApiKey，无需迁移")


if __name__ == "__main__":
    asyncio.run(main())
