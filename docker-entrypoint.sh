#!/bin/bash
set -e

cd /app

# 3rd/ 下的非 PyPI 依赖随代码目录挂载进来，首次启动时补装（已装则跳过）
for whl in /app/3rd/fireredvad-*.whl; do
    [ -e "$whl" ] || continue
    pkg=$(basename "$whl" | sed -E 's/-[0-9].*//')
    if ! pip show "$pkg" >/dev/null 2>&1; then
        echo "[entrypoint] installing $whl"
        pip install --no-cache-dir "$whl"
    fi
done

exec "$@"
