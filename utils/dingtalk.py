# -*- coding: utf-8 -*-
"""钉钉群自定义机器人消息推送（LLM 自动化测试播报等自动化消息）。

地址取 config.yaml THIRD_PARTY_SERVICES 里 subscribe_address 条目下的
webhook。THIRD_PARTY_SERVICES 是「列表嵌 dict」，且本项目沿用标记键 +
同级属性的写法（同 bytedance: "tts" 与同级 url/appid），因此
dingtalk_test_group1 是 subscribe_address 的**同级键**而非其子键：

    THIRD_PARTY_SERVICES:
      - subscribe_address:
        dingtalk_test_group1: "https://oapi.dingtalk.com/robot/send?access_token=***"
        dingtalk_test_group1_secret: "SECxxxx"   # 机器人开了「加签」才需要

默认发往 dingtalk_test_group1，要通知多个群就在同一条目下加键（嵌套写成
subscribe_address: {群名: 地址} 也认），调用处传 name 区分。

安全设置的两种情况本模块都支持：
  - 自定义关键词 / IP 白名单：直接 POST JSON 即可
  - 加签：需要在上面配 <群名>_secret（机器人「安全设置-加签」里以 SEC
    开头的密钥），发送时按钉钉规范追加 timestamp + sign 两个 query 参数
返回体 errcode==0 才算发送成功；310000 一般是安全设置没过（关键词不命中、
签名不匹配/IP 不在白名单），detail 会原样带回 errmsg 便于定位。

所有对外函数只返回 (ok, detail)，不抛异常——通知失败绝不能影响主流程
（测试运行本身），是否落日志由调用方决定。
"""
import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from setting import config_data

DEFAULT_GROUP = "dingtalk_test_group1"
SEND_TIMEOUT = 10
MARKER = "subscribe_address"
SECRET_SUFFIX = "_secret"


def _addresses() -> dict:
    """汇总所有 subscribe_address 条目下的键值（同级键与嵌套键都收）。"""
    out = {}
    for svc in config_data["THIRD_PARTY_SERVICES"]:
        if not isinstance(svc, dict) or MARKER not in svc:
            continue
        for k, v in svc.items():
            if k == MARKER:
                continue  # 标记键自身（同级写法下为 None）
            if isinstance(v, dict):  # 兼容嵌套写法：subscribe_address: {群名: 地址}
                out.update({kk: vv for kk, vv in v.items() if vv})
            elif v:
                out[k] = v
    return out


def get_webhook(name: str = DEFAULT_GROUP):
    """取指定群的 webhook，未配置返回 None（调用方静默跳过通知）。"""
    return _addresses().get(name)


def get_secret(name: str = DEFAULT_GROUP):
    """取指定群的加签密钥（配置键 <群名>_secret），未配置返回 None。"""
    return _addresses().get(name + SECRET_SUFFIX)


def _signed(url: str, secret):
    """机器人开启加签时给 webhook 追加 timestamp + sign，未配密钥原样返回。

    钉钉规范：sign = urlsafe_b64(hmac_sha256(secret, f"{ts}\\n{secret}"))，
    ts 为毫秒时间戳，与 access_token 一起放在 query 上。
    """
    if not secret:
        return url
    ts = str(round(time.time() * 1000))
    digest = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(),
                      hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}timestamp={ts}&sign={sign}"


async def post(url: str, payload: dict, secret: str = None):
    """向指定 webhook POST 一条消息，返回 (ok, detail)。"""
    if not url:
        return False, "未配置钉钉 webhook（config.yaml THIRD_PARTY_SERVICES -> subscribe_address）"
    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
            resp = await client.post(_signed(url, secret), json=payload)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}：{resp.text[:200]}"
        if body.get("errcode") != 0:
            # 310000 多为机器人安全设置（自定义关键词/加签/IP 白名单）不通过
            return False, f"errcode={body.get('errcode')} {body.get('errmsg') or ''}".strip()
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def send_markdown(title: str, text: str, group: str = DEFAULT_GROUP):
    """发一条 markdown 消息到钉钉群，返回 (ok, detail)。"""
    return await post(get_webhook(group), {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text}}, get_secret(group))


async def send_text(content: str, group: str = DEFAULT_GROUP):
    """发一条纯文本消息（联调/简单通知用），返回 (ok, detail)。"""
    return await post(get_webhook(group), {
        "msgtype": "text",
        "text": {"content": content}}, get_secret(group))
