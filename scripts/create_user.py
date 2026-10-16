#!/usr/bin/env python3
"""创建后台管理员账号（User 表）。

用法（在项目根目录或任意目录均可）：
    python3 scripts/create_user.py <username> [选项]

口令来源（三选一，优先级从高到低）：
    --password '明文'          命令行直传（会留在 shell 历史，仅脚本化场景用）
    --password-env VAR         从环境变量读取（推荐在 CI/自动化里用）
    交互输入                    都不传时提示输入并二次确认（推荐人工使用）

口令以 bcrypt 哈希存入 User.hashed_password，与登录接口
（modules/user/views.py 的 bcrypt.checkpw 通路）完全兼容。

选项：
    --role admin|operator      角色，默认 admin
    --nickname '姓名'          真实姓名
    --job '工作描述'
    --phone '手机号'
    --reactivate               同名账号存在但已软删时，复活并重置其口令/信息
    --dry-run                  只校验并预览将要写入的内容，不落库

示例：
    python3 scripts/create_user.py zhangsan
    python3 scripts/create_user.py lisi --role operator --nickname 李四 --dry-run
"""
import argparse
import asyncio
import getpass
import os
import sys

# 保证从任意工作目录运行时都能 import 项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from sqlalchemy import or_, select

from mybatisPlus.tables.industrial_park import User
from mybatisPlus.tables.sqlcli import AsyncSessionLocal, async_engine


def resolve_password(args) -> str:
    if args.password:
        return args.password
    if args.password_env:
        val = os.environ.get(args.password_env)
        if not val:
            sys.exit(f"错误：环境变量 {args.password_env} 未设置或为空")
        return val
    while True:
        p1 = getpass.getpass("输入口令（输入不回显）: ")
        if len(p1) < 6:
            print("口令至少 6 位，请重试。")
            continue
        p2 = getpass.getpass("再次输入确认: ")
        if p1 != p2:
            print("两次输入不一致，请重试。")
            continue
        return p1


async def create_user(args) -> int:
    plain = resolve_password(args)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # username 有唯一索引：软删行同样占用，必须一并查出处理
            exist = await session.scalar(select(User).filter_by(username=args.username))
            if exist:
                alive = exist.is_delete is None or exist.is_delete is False
                if alive:
                    print(f"错误：账号 '{args.username}' 已存在（id={exist.id}）。"
                          f"如需改口令请人工 UPDATE，或换用户名。")
                    return 1
                if not args.reactivate:
                    print(f"错误：账号 '{args.username}' 存在但已软删（id={exist.id}）。"
                          f"加 --reactivate 可复活并重置口令。")
                    return 1
                exist.is_delete = False
                exist.hashed_password = hashed
                for k, v in (("role", args.role), ("nickname", args.nickname),
                             ("job", args.job), ("phone_number", args.phone)):
                    if v is not None:
                        setattr(exist, k, v)
                session.add(exist)
                target, action = exist, "复活"
            else:
                target = User(username=args.username, hashed_password=hashed,
                              role=args.role or "admin", nickname=args.nickname,
                              job=args.job, phone_number=args.phone, is_delete=False)
                session.add(target)
                action = "创建"

            if args.dry_run:
                await session.rollback()
                print(f"[dry-run] {action}预览（未写库）：id={'现有行' if exist else '新行'} "
                      f"username={args.username} role={target.role} "
                      f"nickname={target.nickname} phone={target.phone_number}")
                return 0

            await session.flush()
            print(f"已{action}管理员：id={target.id} username={args.username} role={target.role}")
            return 0


def main():
    ap = argparse.ArgumentParser(description="创建后台管理员账号（User 表）",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("示例：")[-1])
    ap.add_argument("--username", help="登录用户名（全局唯一）")
    ap.add_argument("--password", help="明文口令（会留 shell 历史，建议交互输入或 --password-env）")
    ap.add_argument("--password-env", metavar="VAR", help="从指定环境变量读取口令")
    ap.add_argument("--role", default="admin",
                    help="角色，默认 admin（库里现存 admin/user，取值自由填写）")
    ap.add_argument("--nickname", help="真实姓名")
    ap.add_argument("--job", help="工作描述")
    ap.add_argument("--phone", help="电话号码")
    ap.add_argument("--reactivate", action="store_true",
                    help="同名账号已软删时复活并重置口令")
    ap.add_argument("--dry-run", action="store_true", help="只预览不落库")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args)))


async def run(args):
    """包一层：确保退出前释放连接池，避免 aiomysql 在已关闭的 loop 上析构连接刷栈。"""
    try:
        return await create_user(args)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    main()
