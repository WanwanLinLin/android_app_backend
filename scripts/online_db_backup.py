#!/usr/bin/env python3
"""线上库全量备份（结构 DDL + 数据）+ checksum 基线。

用法：
    ONLINE_DB=IndustrialPark python3 scripts/online_db_backup.py

产出（默认写到项目根 backup/<库名>_<时间戳>/）：
    schema.sql        每张表的 SHOW CREATE TABLE
    data.sql          每张表的全量 INSERT
    checksums.txt     每表行数 + 内容 sha256，作为迁移前后回归比对基线

只读操作，不写任何数据。
"""
import hashlib
import os
import sys
from datetime import datetime

import pymysql

DB = os.environ.get("ONLINE_DB", "IndustrialPark")
HOST = os.environ.get("DB_HOST", "192.168.1.52")
PORT = int(os.environ.get("DB_PORT", "3390"))
USER = os.environ.get("DB_USER", "root")
PWD = os.environ.get("DB_PWD", "linwan")

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = os.environ.get("BACKUP_DIR", f"backup/{DB}_{STAMP}")


def tables(cur):
    cur.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
        (DB,),
    )
    return [r[0] for r in cur.fetchall()]


def sql_quote(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return "0x" + v.hex()
    s = str(v)
    repl = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\0": "\\0",
            "\x1a": "\\Z"}
    for k, val in repl.items():
        s = s.replace(k, val)
    return "'" + s + "'"


def main():
    os.makedirs(OUT, exist_ok=True)
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD,
                           database=DB, charset="utf8mb4",
                           connect_timeout=15, cursorclass=pymysql.cursors.Cursor)
    cur = conn.cursor()
    tbls = tables(cur)
    if not tbls:
        print("RESULT NO_TABLES —— 库名或权限有误")
        sys.exit(1)

    schema_path = os.path.join(OUT, "schema.sql")
    data_path = os.path.join(OUT, "data.sql")
    sum_path = os.path.join(OUT, "checksums.txt")

    lines_sum = []
    with open(schema_path, "w", encoding="utf-8") as fs, \
            open(data_path, "w", encoding="utf-8") as fd:
        fs.write(f"-- schema dump of `{DB}` @ {HOST}:{PORT}  {STAMP}\n\n")
        fd.write(f"-- data dump of `{DB}` @ {HOST}:{PORT}  {STAMP}\n\n")
        fd.write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n\n")
        for t in tbls:
            cur.execute(f"SHOW CREATE TABLE `{t}`")
            ddl = cur.fetchone()[1]
            fs.write(f"DROP TABLE IF EXISTS `{t}`;\n{ddl};\n\n")

            cur.execute(f"SELECT * FROM `{t}`")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            fd.write(f"-- {t} ({len(rows)} rows)\n")
            if rows:
                collist = ",".join(f"`{c}`" for c in cols)
                for r in rows:
                    vals = ",".join(sql_quote(x) for x in r)
                    fd.write(f"INSERT INTO `{t}` ({collist}) VALUES ({vals});\n")
            fd.write("\n")

            # checksum：按主键/全列排序后的内容哈希，避免行序影响
            order_cols = cols
            h = hashlib.sha256()
            for r in sorted(rows, key=lambda x: [sql_quote(v) for v in x]):
                h.update(repr(r).encode("utf-8"))
            lines_sum.append(f"{t}\trows={len(rows)}\tsha256={h.hexdigest()}")
        fd.write("\nSET FOREIGN_KEY_CHECKS=1;\n")

    with open(sum_path, "w", encoding="utf-8") as f:
        f.write(f"# checksum baseline {DB} @ {STAMP}\n")
        f.write("\n".join(lines_sum) + "\n")

    conn.close()
    print("RESULT OK")
    print("OUT", os.path.abspath(OUT))
    print("TABLES", len(tbls))
    for l in lines_sum:
        print("SUM", l)


if __name__ == "__main__":
    main()
