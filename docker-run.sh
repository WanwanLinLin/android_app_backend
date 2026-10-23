#!/bin/bash
# 数字人对话后端 —— 容器启动脚本（代码挂载，不打进镜像）
#
# 用法： ./docker-run.sh            前台交互模式（Ctrl+C 停止）
#        MODE=d ./docker-run.sh     后台守护模式（docker logs -f android-backend 看日志）
set -e

# 项目宿主机路径（代码挂载源，改这里即可换机器）
PROJECT_DIR="${PROJECT_DIR:-/home/linwan/cproject/android_app_backend}"
IMAGE="android-backend:1.0"
NAME="android-backend"

# 清理同名旧容器
docker rm -f "$NAME" >/dev/null 2>&1 || true

# --network host : 容器直接复用宿主机网络栈。
#   服务监听 8852（config.yaml SERVICES[0].port）；出站访问 192.168.1.52 的
#   MySQL(3390) / Redis(6390) 也走宿主机网络，避免 bridge 下无法访问内网地址的问题。
# 挂载：
#   /app        项目代码 + config.yaml + static/ + 3rd/ 原生 whl（首次启动 entrypoint 自动补装）
#   /app/logs   日志独立挂载，避免写宿主机项目目录时的权限噪音
#   /data       TTS 等缓存目录（config.yaml CACHE.* 指向 /data/cache/...）
# fireredvad 的 native 库需要 GLIBCXX_3.4.32（GCC13+ 编译），镜像内 bookworm 的
# libstdc++ 只到 3.4.30。宿主机(Ubuntu 22.04)自带 6.0.35（含 3.4.35），
# 挂进容器顶替即可，无需重建镜像。
STDCXX_HOST="/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.35"
STDCXX_OPTS=()
if [ -e "$STDCXX_HOST" ]; then
    STDCXX_OPTS=(
        -v "$STDCXX_HOST:/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.34:ro"
        -e "LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.34"
    )
else
    echo "警告: 未找到 $STDCXX_HOST，fireredvad 可能因 GLIBCXX 版本不足而导入失败" >&2
fi

MOUNTS=(
    -v "${PROJECT_DIR}:/app"
    -v "${PROJECT_DIR}/logs:/app/logs"
    -v "/data:/data"
    "${STDCXX_OPTS[@]}"
)

if [ "${MODE}" = "d" ]; then
    docker run -d --name "$NAME" --restart unless-stopped --network host \
        "${MOUNTS[@]}" -w /app "$IMAGE"
    echo "started: $NAME  ->  http://127.0.0.1:8852"
    echo "logs:    docker logs -f $NAME"
else
    docker run --rm -it --name "$NAME" --network host \
        "${MOUNTS[@]}" -w /app "$IMAGE"
fi
