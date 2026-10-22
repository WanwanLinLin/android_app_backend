#!/usr/bin/env python3
"""存量资源迁移：TTS/ASR/LLM Factories 行 → 个性插件（CustomPlugin）。

资源体系重构（基础插件 = utils/providers 代码文件登记 + 个性插件 = 用户自带
JSON 配置）落地后，把三张旧资源池表的存量数据整体转成个性插件，并把 SourceList
中的旧类型绑定（TTS/ASR/LLM）改写为新类型（TTS_CUSTOM/ASR_CUSTOM/LLM_CUSTOM）
与新 id。

归属口径（2026-10-22 调整）：个性插件**严格私有**，不再有"平台归属/共享"
（owner_id=NULL）概念。存量 Factories 行统一归属主账号 hopesen（按用户名
DEFAULT_OWNER_USERNAME 解析其 User.id，线上/本地 id 可能不同）。

行为：
  1. 确保 BasePlugin 登记与磁盘插件目录一致（同列表接口的自动登记逻辑）；
  2. 每条有效 Factories 行 → 一条 CustomPlugin：
       name  = "<desc 或 表名+id>"，category = 表类别，
       base_plugin_id = 按 Factories.type（TTS 用 tag）匹配 BasePlugin.name；
       config = 该行完整配置（type/url/apikey/params/voice…）；
       owner_id = hopesen 的 User.id。
     幂等：同一 owner 且同 (category, name, base_plugin_id) 的个性插件视为已迁移，
     直接复用其 id，不重复创建。
  3. SourceList：type ∈ (TTS,ASR,LLM) 的存量绑定 → (TTS_CUSTOM/..., 新id)。
     资源行匹配不到基础插件（type/tag 不在磁盘插件中）时**跳过并报告**，
     绑定保持旧类型（旧链路仍可用，待管理员处理）。
  4. 旧 Factories 表数据保留不动（不删不改），仅停止前台展示。

安全：
  - **默认 dry-run**，只打印将要执行的变更；--execute 才真正写库。
  - 线上库（IndustrialPark）执行前先跑 scripts/online_db_backup.py 全量备份。
  - 单事务执行，任何一步异常整体回滚。

用法（项目根目录）：
    python3 scripts/migrate_resources_to_custom_plugins.py            # 预览
    python3 scripts/migrate_resources_to_custom_plugins.py --execute  # 执行
    指定库：DB_URL=mysql+asyncmy://user:pwd@host:port/dbname ...
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_, select

from mybatisPlus.tables.industrial_park import (ASRFactories, BasePlugin, CustomPlugin,
                                                LLMFactories, SourceList, TTSFactories,
                                                User, STATUS_ACTIVE)
from mybatisPlus.tables.sqlcli import AsyncSessionLocal, async_engine
from mybatisPlus.base_plugin_orm import sync_disk_plugins
from utils.common.enumTaskType import SourceTypeEnum

# 存量 Factories 行的归属主账号（个性插件严格私有，无平台归属）
DEFAULT_OWNER_USERNAME = "hopesen"

TABLES = {
    "TTS": TTSFactories,
    "ASR": ASRFactories,
    "LLM": LLMFactories,
}
# config 序列化时携带的列（其余列如 create_time/status/is_delete 不进 config）
# TTS 参数列 2026-10-22 由 additional_param 改名为 params，三表键位统一
CONFIG_COLS = {
    "TTS": ("type", "url", "desc", "tag", "voice", "apikey", "params"),
    "ASR": ("type", "url", "desc", "apikey", "params"),
    "LLM": ("type", "url", "apikey", "desc", "params"),
}

# 幂等口径：同 owner + 同 category + 同名 + 同基础插件 视为已迁移。
# 曾用 desc 尾部 "[migrated_from:TTS#1]" 标记做幂等，因影响前端展示已于
# 2026-10-22 清除（存量标记由一次性 UPDATE 移除，本脚本同步改为名称匹配）。


def _alive(m):
    return or_(m.is_delete.is_(None), m.is_delete.is_(False))


async def main(execute: bool):
    report = []
    async with AsyncSessionLocal() as session:
        added = await sync_disk_plugins(session)
        report.append(f"BasePlugin 自动登记：新增 {added} 条")
        bases = {}  # (category, name) -> BasePlugin
        for b in (await session.scalars(select(BasePlugin).where(_alive(BasePlugin)))).all():
            bases[(b.category, b.name)] = b

        # 存量插件归属主账号（严格私有，无平台归属）。按用户名解析 id，兼容线上/本地 id 不同
        owner = await session.scalar(select(User).filter_by(username=DEFAULT_OWNER_USERNAME))
        if owner is None:
            raise SystemExit(f"❌ 未找到归属主账号用户 {DEFAULT_OWNER_USERNAME!r}，"
                             f"请先确认该库中存在此账号（或改 DEFAULT_OWNER_USERNAME）")
        owner_id = owner.id
        report.append(f"存量插件归属：{DEFAULT_OWNER_USERNAME}（User.id={owner_id}）")

        id_map = {}  # (category, old_id) -> new CustomPlugin.id
        skipped = []
        # 幂等索引：(category, name, base_plugin_id) -> CustomPlugin.id（仅归属主账号的行）。
        # 已迁移过的行按名称复用，不再重复创建。
        migrated = {}
        for c in (await session.scalars(select(CustomPlugin).where(
                _alive(CustomPlugin), CustomPlugin.owner_id == owner_id))).all():
            migrated[(c.category, c.name, c.base_plugin_id)] = c.id
        for category, model in TABLES.items():
            rows = (await session.scalars(
                select(model).where(_alive(model)).order_by(model.id))).all()
            for row in rows:
                # provider 文件名：TTS 用 tag（stream 链路如此约定），ASR/LLM 用 type
                plugin_name = row.tag if category == "TTS" else row.type
                base = bases.get((category, plugin_name))
                if base is None:
                    skipped.append((category, row.id, plugin_name))
                    continue
                name = f"{row.desc or f'{category} 资源 #{row.id}'}"[:128]
                existed = migrated.get((category, name, base.id))
                if existed:
                    id_map[(category, row.id)] = existed
                    continue
                cfg = {c: getattr(row, c, None) for c in CONFIG_COLS[category]}
                plugin = CustomPlugin(name=name, category=category,
                                      base_plugin_id=base.id,
                                      desc=(row.desc or '')[:200] or None,
                                      config=cfg, owner_id=owner_id, is_delete=False)
                session.add(plugin)
                await session.flush()
                id_map[(category, row.id)] = plugin.id
                migrated[(category, name, base.id)] = plugin.id

        # SourceList 旧类型绑定 → *_CUSTOM 新 id
        bind_updates = []
        binds = (await session.scalars(
            select(SourceList).where(SourceList.type.in_(tuple(TABLES.keys())))
            .where(_alive(SourceList)))).all()
        for s in binds:
            new_id = id_map.get((s.type, s.reference_id))
            if new_id is None:
                continue  # 资源未迁移（插件名对不上），保持旧绑定
            bind_updates.append((s.id, s.type, s.reference_id,
                                 SourceTypeEnum.to_custom(s.type), new_id))
            s.type = SourceTypeEnum.to_custom(s.type)
            s.reference_id = new_id
            session.add(s)

        report.append(f"迁移个性插件：{len(id_map)} 条（含已迁移复用的）")
        if skipped:
            report.append(f"⚠ 未匹配到基础插件（保持原状待处理）：{len(skipped)} 条")
            for category, rid, pname in skipped:
                report.append(f"    - {category} #{rid} → 插件名 {pname}（磁盘上无此插件文件/未登记）")
        report.append(f"SourceList 绑定改写：{len(bind_updates)} 条")
        for bid, ot, orid, nt, nid in bind_updates:
            report.append(f"    - SourceList #{bid}: {ot}#{orid} → {nt}#{nid}")

        print("\n".join(report))
        if execute:
            await session.commit()
            print("\n✅ 已提交")
        else:
            await session.rollback()
            print("\n（dry-run，未写库。加 --execute 真正执行）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="真正写库（默认 dry-run）")
    args = parser.parse_args()
    asyncio.run(main(args.execute))
