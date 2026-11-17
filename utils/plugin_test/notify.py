# -*- coding: utf-8 -*-
"""LLM 自动化测试结果播报到钉钉群。

时机（2026-11-17 与用户确认）：只播【定时运行】的结果——手动「立即运行 /
一键测试」属调试行为，不刷群。任务级开关 PluginTestTask.notify_dingtalk
（新建默认开启）可逐任务关掉播报。

两类消息（均由调度器发出，见 utils/plugin_test/scheduler.py）：
  - notify_report ：任务跑完播结果摘要 + 失败明细（报告里带 trigger 与
                    notify_dingtalk 快照，这里再校验一次，双保险）
  - notify_failure：定时任务整体执行异常（跑挂了，比跑输更需要被看到）

展示口径（2026-11-17 用户定）：消息里「测试任务」显示后台配置的**任务描述**
（面向群成员，描述比内部任务名更可读）；描述为空或空白则退回任务名。

发送失败只落日志，绝不影响测试主流程与调度器顺延。地址配置见 utils.dingtalk。
"""
from utils.getLogs import scheduled_task_logger
from utils import dingtalk

# 失败明细最多列几条——群里看得完比全量重要，完整明细在后台报告/PDF
MAX_FAIL_LINES = 8
# 单条失败原因在群消息里的截断长度
FAIL_REASON_LIMIT = 120

_RULE_LABEL = {"contains": "应包含", "not_contains": "不应包含",
               "regex": "应匹配正则", "llm_judge": "AI 判定"}


def _one_line(text, limit: int = FAIL_REASON_LIMIT) -> str:
    """压成单行并截断——报告里的原因可能带换行与长输出摘录。"""
    t = " ".join(str(text or "").split())
    return t[:limit] + "…" if len(t) > limit else t


def _fail_reason(item: dict) -> str:
    """一个失败插件的简明原因：优先调用错误，其次第一条未通过的规则。"""
    if item.get("error"):
        return _one_line(item["error"])
    for c in item.get("checks") or []:
        if not c.get("passed"):
            label = _RULE_LABEL.get(c.get("type"), c.get("type"))
            return _one_line(f"{label}「{c.get('value')}」未通过："
                             f"{c.get('detail') or '（无明细）'}")
    return "未通过（无明细）"


def _task_label(report: dict) -> str:
    """群里「测试任务」展示的内容：用后台配置的**任务描述**，未填描述退回任务名。

    （用户 2026-11-17 口径：播报面向群成员，描述比内部任务名更可读。）
    描述可能被存成空白串（建任务时不强制非空），strip 后为空即视为未填。
    """
    for key in ("task_desc", "task_name"):
        v = str(report.get(key) or "").strip()
        if v:
            return v
    return "未知"


def build_markdown(report: dict):
    """由测试报告生成群消息 (title, markdown_text)。"""
    summary = report.get("summary") or {}
    total, ok = summary.get("total") or 0, summary.get("ok") or 0
    items = report.get("items") or []
    bad = [i for i in items if not i.get("ok")]
    passed = not bad and total > 0
    trigger = "每日定时" if report.get("trigger") == "scheduled" else "手动运行"
    title = (f"LLM自动化测试通过（{ok}/{total}）" if passed
             else f"LLM自动化测试失败（{ok}/{total} 通过）")

    lines = [f"### {'✅' if passed else '❌'} {title}",
             f"- **测试任务**：{_task_label(report)}（#{report.get('task_id')}）",
             f"- **运行时间**：{report.get('run_time')}（{trigger}）"]
    seconds = sum(i.get("seconds") or 0 for i in items)
    if seconds:
        lines.append(f"- **总耗时**：{round(seconds, 1)}s")
    lines.append("")

    if passed:
        lines += [f"- ✅ {i.get('plugin_name')}（#{i.get('plugin_id')}）"
                  for i in items[:MAX_FAIL_LINES]]
        if len(items) > MAX_FAIL_LINES:
            lines.append(f"- …另有 {len(items) - MAX_FAIL_LINES} 个插件通过")
    else:
        for i in bad[:MAX_FAIL_LINES]:
            lines.append(f"- ❌ {i.get('plugin_name')}（#{i.get('plugin_id')}）"
                         f"：{_fail_reason(i)}")
        if len(bad) > MAX_FAIL_LINES:
            lines.append(f"- …另有 {len(bad) - MAX_FAIL_LINES} 个插件失败")
        lines.append("")
        lines.append("完整明细见后台「测试结果 / 历史测试记录」，可导出 PDF。")
    return title, "\n".join(lines)


def _notify_enabled(report: dict) -> bool:
    """报告快照里的开关（旧报告无该字段视为开启，与建表默认一致）。"""
    return report.get("notify_dingtalk") is not False


async def notify_report(report: dict):
    """定时运行完成后播报结果。返回是否实际发送成功；内部不抛异常。"""
    if (report or {}).get("trigger") != "scheduled":
        return False  # 手动运行不播，避免调试刷群
    if not _notify_enabled(report):
        scheduled_task_logger.info(
            f"LLM自动化测试 任务#{report.get('task_id')} 已关闭钉钉播报，跳过")
        return False
    try:
        title, text = build_markdown(report)
    except Exception as e:
        scheduled_task_logger.error(f"LLM自动化测试 钉钉播报生成消息失败: {e}")
        return False
    ok, detail = await dingtalk.send_markdown(title, text)
    scheduled_task_logger.info(
        f"LLM自动化测试 钉钉播报 任务#{report.get('task_id')} 运行#{report.get('run_id')} "
        f"→ {'成功' if ok else f'失败（{detail}）'}")
    return ok


async def notify_failure(task_id: int, err):
    """定时任务整体执行异常告警（展示用的任务信息与开关从库里现查）。"""
    from mybatisPlus.plugin_test_orm import get_task_notify_info
    name, desc, notify = await get_task_notify_info(task_id)
    if notify is False:
        scheduled_task_logger.info(
            f"LLM自动化测试 任务#{task_id} 已关闭钉钉播报，跳过异常告警")
        return False
    title = "LLM自动化测试执行异常"
    text = ("### ⚠️ LLM自动化测试执行异常\n"
            f"- **测试任务**：{_task_label({'task_desc': desc, 'task_name': name})}（#{task_id}）\n"
            "- **触发方式**：每日定时\n"
            f"- **异常信息**：{_one_line(err, 300)}\n\n"
            "本次定时运行未完成、结果未更新，请到后台检查被测插件与服务。")
    ok, detail = await dingtalk.send_markdown(title, text)
    scheduled_task_logger.info(
        f"LLM自动化测试 钉钉异常告警 任务#{task_id} → {'成功' if ok else f'失败（{detail}）'}")
    return ok
