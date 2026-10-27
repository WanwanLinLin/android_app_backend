"""apikey / Authorization 等敏感字段的展示掩码与保存回填。

背景：后台列表/详情接口会把插件配置（config / default_config / params）原样
返回，其中 apikey、params.headers.Authorization 等敏感值会直接暴露给所有登录
后台的管理员。2026-10-27 起统一在**展示出口**掩码。

两层机制（缺一不可）：
  1. 展示层 mask_secrets：列表/详情接口返回前，把敏感键的值替换为 "***"。
     掩码只发生在 HTTP 视图出口——websocket 运行链
     （get_source_config / resolve_runtime_config / get_one_voice 等）不经过
     掩码，真实 key 照常供 provider 使用。
  2. 保存层 restore_masked：编辑表单提交的是**已掩码**的展示值，若原样落库
     会用 "***" 覆盖真实 key。更新接口在写库前调用本函数，把敏感键位置上
     仍为 "***" 的值恢复为库里原值（用户没改过就等于没改）。

敏感键判定（归一化：转小写、剔除非字母数字后做子串匹配）：
  - 含 "apikey"：apikey / api_key / X-Api-Key / apikey_secret …
  - 含 "authorization"：authorization / proxy_authorization …
递归处理嵌套 dict（params.headers.Authorization 等）。值为 None/空串时保留
原值不掩码（避免把"未配置"显示成 "***" 误导）。
"""

MASK = "***"


def _normalized_key(key) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def is_secret_key(key) -> bool:
    n = _normalized_key(key)
    return "apikey" in n or "authorization" in n


def mask_secrets(obj):
    """递归掩码敏感键的值，返回新对象，不修改入参。"""
    if isinstance(obj, dict):
        return {k: (MASK if is_secret_key(k) and obj[k] not in (None, "")
                    else mask_secrets(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_secrets(x) for x in obj]
    return obj


def restore_masked(new, old):
    """保存回填：new 中敏感键位置的值仍为 MASK 时，恢复为 old 同键的原值。

    old 中无原值（或原值为空）时保留 MASK 原样提交——这类键本就未配置过，
    行为与用户手填 "***" 一致。仅递归 dict（config/params 均为 dict 结构）。
    """
    if not isinstance(new, dict):
        return new
    result = {}
    for k, v in new.items():
        if is_secret_key(k):
            if v == MASK and isinstance(old, dict) and old.get(k) not in (None, MASK, ""):
                result[k] = old[k]
            else:
                result[k] = v
        elif isinstance(v, dict):
            result[k] = restore_masked(v, old.get(k) if isinstance(old, dict) else None)
        else:
            result[k] = v
    return result
