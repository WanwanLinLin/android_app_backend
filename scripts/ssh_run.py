#!/usr/bin/env python3
"""在 192.168.1.52 上执行一条命令并回显（部署前端用的小工具）。

用 paramiko（纯 socket，不依赖 PTY——沙箱里 /dev/pts 可能整个缺失，pexpect 会挂）。
密码从环境变量 SSH_PWD 或 skills/quick-dev.md 读取，不落盘、不打印。
需解释器装有 paramiko：conda 环境 android-backend 已装（pexpect 反而只有系统 python3 有）。

用法：
    python3 scripts/ssh_run.py "ls -la /data/hbh/cproject/IndustrialPark/dist"
上传：
    python3 scripts/ssh_run.py --put <本地文件> <远端路径>
"""
import os
import re
import sys

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.1.52")
USER = os.environ.get("DEPLOY_USER", "hbh")
TIMEOUT = int(os.environ.get("DEPLOY_TIMEOUT", "300"))


def password():
    pwd = os.environ.get("SSH_PWD")
    if pwd:
        return pwd
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "skills", "quick-dev.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"ssh\s+\w+@" + HOST + r"\s*\n\s*密码：(\S+)", text)
    if not m:
        raise SystemExit("未能从 skills/quick-dev.md 解析出密码，请设 SSH_PWD 环境变量")
    return m.group(1)


def client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=password(), timeout=20,
              look_for_keys=False, allow_agent=False)
    return c


def run(cmd):
    c = client()
    try:
        _, out, err = c.exec_command(cmd, timeout=TIMEOUT)
        text = out.read().decode("utf-8", "replace").strip()
        code = out.channel.recv_exit_status()
        if text:
            print(text)
        stderr_text = err.read().decode("utf-8", "replace").strip()
        if stderr_text:
            print("[stderr]", stderr_text[:2000], file=sys.stderr)
        print(f"__EXIT__={code}")
        return code
    finally:
        c.close()


def put(local, remote):
    c = client()
    try:
        sftp = c.open_sftp()
        sftp.put(local, remote)
        sftp.close()
        print(f"上传完成 {local} -> {remote}")
        print("__EXIT__=0")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--put":
        sys.exit(put(sys.argv[2], sys.argv[3]))
    sys.exit(run(" ".join(sys.argv[1:]) or "echo ok"))
