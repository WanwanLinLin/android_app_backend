# 数字人对话后端 (android_app_backend) 运行镜像
# 代码不打进镜像：运行时用 -v 挂载项目目录到 /app
#
# 构建：
#   docker build -t android-backend:1.0 .
# 运行（见 docker-run.sh，或）：
#   docker run -d --name android-backend --network host \
#     -v /home/linwan/cproject/android_app_backend:/app \
#     -w /app android-backend:1.0

FROM python:3.12-slim-bookworm

# libopus0 : opuslib_next / 音频编解码
# libsndfile1 : soundfile
# ffmpeg : pydub 音频转换兜底
# 换用阿里云 debian 源（官方源在国内下载极慢）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
        libopus0 \
        libsndfile1 \
        ffmpeg \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 依赖层打进镜像（requirements.txt 只含 PyPI 包，构建期从 COPY 读取）
# opuslib_next：voice_handler.py 直接 import，但未列进项目 requirements.txt（本地环境手工装的），
# 这里显式补上，否则容器起不来。
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt opuslib-next

# 注意：fireredvad 的 native .so 需要 GLIBCXX_3.4.32，bookworm 自带 libstdc++ 只到
# 3.4.30（backports 也没有更高版本）。解决方案在 docker-run.sh：把宿主机
# (Ubuntu 22.04, libstdc++ 6.0.35) 的 so 挂进容器并 LD_PRELOAD，镜像本身不动。

# 镜像内置启动脚本：等依赖 whl 就位（3rd/ 随代码挂载）→ 补装 → 启动
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8852

# 服务端口取自挂载的 config.yaml SERVICES[0].port（当前 8852）
CMD ["python3", "run.py"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
