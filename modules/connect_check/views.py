import asyncio
import time
from urllib.parse import urlparse

from . import schema
from fastapi import APIRouter, status, Depends
from utils.common.schema import GeneticResponse
from utils.admin_auth import current_admin

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# scheme → 默认端口（覆盖资源表 url 字段的常见形态：http/https/ws/wss）
DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _resolve_target(url: str, port: int = None):
    """从 URL 解析 (host, port)。无 scheme 时按裸 ip/域名处理，端口必填或取传入值。

    返回 (host, port) 或抛 ValueError（信息直接透出给前端）。
    """
    url = url.strip()
    if not url:
        raise ValueError("地址为空")
    parsed = urlparse(url if "//" in url else "//" + url)
    host = parsed.hostname
    if not host:
        raise ValueError("无法从地址中解析出主机")
    # 显式端口优先，其次 URL 内端口，再次 scheme 默认端口
    if port:
        target_port = port
    elif parsed.port:
        target_port = parsed.port
    elif parsed.scheme in DEFAULT_PORTS:
        target_port = DEFAULT_PORTS[parsed.scheme]
    else:
        raise ValueError("地址未含端口，请补充端口号")
    if not (0 < int(target_port) < 65536):
        raise ValueError("端口不合法")
    return host, int(target_port)


async def _tcp_probe(host: str, port: int, timeout: float):
    """TCP 三次握手探测：能建连即视为连通。返回 (ok, latency_ms, err)。"""
    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass  # 关闭阶段的异常不影响连通性结论
        return True, round((time.perf_counter() - start) * 1000, 1), None
    except asyncio.TimeoutError:
        return False, None, f"连接超时（>{timeout:.0f}s）"
    except OSError as e:
        return False, None, str(e) or e.__class__.__name__


@router.post("/v1/connectCheck", summary="检测资源连通性（ip:端口 / 域名）", tags=["通用接口"])
async def _connect_check(info: schema.ConnectCheckModel, admin: dict = Depends(current_admin)):
    """对资源的 url（或裸主机）做 TCP 连通性探测，返回是否连通、耗时与失败原因。

    仅做传输层建连检测，不校验应用层协议/密钥是否正确。
    """
    try:
        host, port = _resolve_target(info.url, info.port)
    except ValueError as e:
        return GeneticResponse(code=400, msg=str(e))
    timeout = min(max(info.timeout or 3, 1), 10)
    ok, latency, err = await _tcp_probe(host, port, timeout)
    return GeneticResponse(data={
        "reachable": ok,
        "host": host,
        "port": port,
        "latency_ms": latency,
        "error": err,
    })
