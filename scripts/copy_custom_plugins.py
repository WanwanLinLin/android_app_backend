#!/usr/bin/env python3
"""把一个用户的个性插件（CustomPlugin）整体复制给另一个用户。

对**当前 config.yaml 指向的库**操作：从 from_user 读出全部有效（未软删）的
个性插件，逐条插入新行给 to_user，仅 owner_id 改为 to_user.id，
name / category / base_plugin_id / desc / config 原样复制（config 深拷贝）。

不跨库硬编码：本地库和线上库各跑一遍（各自切 config 指向），
从本库读、写本库，天然适配两库 id 差异。

用法（在项目根目录或任意目录均可）：
    python3 scripts/copy_custom_plugins.py --from bolan --to hbh [--dry-run]

防重复：若 to_user 已存在「同类别 + 同名」的有效个性插件，则跳过该条
（重复执行不会翻倍）。

选项：
    --from <username>   源用户（提供插件的一方）
    --to   <username>   目标用户（接收复制的一方）
    --dry-run           只预览将写入的内容，不落库
"""
import argparse
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_, select

from mybatisPlus.tables.industrial_park import User, CustomPlugin
from mybatisPlus.tables.sqlcli import AsyncSessionLocal, async_engine, ASYNC_SQLALCHEMY_DATABASE_URL


def _alive():
    return or_(CustomPlugin.is_delete.is_(None), CustomPlugin.is_delete.is_(False))


async def copy_plugins(args) -> int:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            from_u = await session.scalar(select(User).filter_by(username=args.src))
            to_u = await session.scalar(select(User).filter_by(username=args.dst))
            if not from_u:
                print(f"错误：源用户 '{args.src}' 不存在")
                return 1
            if not to_u:
                print(f"错误：目标用户 '{args.dst}' 不存在")
                return 1

            # 源用户的全部有效个性插件
            src_plugins = list((await session.scalars(
                select(CustomPlugin).filter_by(owner_id=from_u.id).where(_alive())
            )).all())
            if not src_plugins:
                print(f"源用户 '{args.src}'（id={from_u.id}）没有任何有效个性插件，无需操作。")
                return 0

            # 目标用户已有的 (category, name) 有效行，用于防重复
            dst_existing = set((await session.execute(
                select(CustomPlugin.category, CustomPlugin.name)
                .filter_by(owner_id=to_u.id).where(_alive())
            )).all())

            added, skipped = 0, 0
            for p in src_plugins:
                if (p.category, p.name) in dst_existing:
                    print(f"  [跳过] {p.category}/{p.name}（目标已有同名同类别插件）")
                    skipped += 1
                    continue
                cfg = copy.deepcopy(p.config) if p.config else None
                new = CustomPlugin(
                    name=p.name, category=p.category, base_plugin_id=p.base_plugin_id,
                    desc=p.desc, config=cfg, owner_id=to_u.id, is_delete=False)
                session.add(new)
                dst_existing.add((p.category, p.name))
                added += 1
                print(f"  [复制] id={p.id} {p.category}/{p.name} base={p.base_plugin_id} "
                      f"-> owner={to_u.id}")

            if args.dry_run:
                await session.rollback()
                print(f"[dry-run] 指向库: {ASYNC_SQLALCHEMY_DATABASE_URL}")
                print(f"[dry-run] 将复制 {added} 条，跳过 {skipped} 条（未写库）")
                return 0

            await session.flush()
            print(f"完成：指向库 {ASYNC_SQLALCHEMY_DATABASE_URL}")
            print(f"  复制 {added} 条，跳过 {skipped} 条，"
                  f"目标用户 '{args.dst}'（id={to_u.id}）")
            return 0


def main():
    ap = argparse.ArgumentParser(
        description="把某用户的个性插件整体复制给另一用户（对当前 config 指向库操作）",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--from", dest="src", required=True, help="源用户（提供插件）")
    ap.add_argument("--to", dest="dst", required=True, help="目标用户（接收复制）")
    ap.add_argument("--dry-run", action="store_true", help="只预览不落库")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args)))


async def run(args):
    try:
        return await copy_plugins(args)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    main()
