"""LLM 自动化测试执行器：多轮真实对话 + 自定义规则校验 + 判定模型。

一次运行（run_task）= 对任务选定的每个 LLM 个性插件：
  1. 运行时解析（resolve_runtime_config，插件不可用直接判失败并给出原因）
  2. importlib 加载 provider（与 modules/stream/views.py 对话链完全同型）
  3. 在同一会话里按 test_prompts 顺序逐轮提问（最多 MAX_TURNS=10 轮，
     session_id 全程一致以延续工作流上下文），收集每轮输出
  4. 按任务规则校验「全部对话内容」——关键字/正则作用于所有轮次
     回复的合并文本；llm_judge 把完整对话记录（逐轮问+答）交给判定模型

规则类型（rules 列表元素，均带 type/value）：
  - contains      对话输出须包含片段（大小写不敏感）
  - not_contains  对话输出不得包含片段
  - regex         对话输出须匹配正则
  - llm_judge     把「完整对话记录 + 判定要求」交给判定模型打分（思考模式
                  开启），模型首行回 PASS/FAIL、正文给充分理由（FAIL 须
                  引用轮次原文），理由随报告明细透出（判定模型取 config.yaml
                  THIRD_PARTY_SERVICES -> generic_llm -> Qwen3.8-fash-next）
规则为空时只测联通性（能拿到非空输出即通过）。

本模块（含调度器、路由的后台执行分支）日志统一走
utils.getLogs.scheduled_task_logger，落 logs/ScheduledTask/ 按日滚动文件。
"""
import asyncio
import importlib
import re
import time
import uuid

import httpx
import openai

from setting import config_data
from utils.common.enumTaskType import WebsocketConnectionEvent
from utils.getLogs import scheduled_task_logger
from mybatisPlus.custom_plugin_orm import resolve_runtime_config, PluginUnavailableError
from mybatisPlus.tables.sqlcli import AsyncSessionLocal

# 单个插件「一轮」调用的超时（秒）：rhn_workflow / ragflow 内部 aiohttp 默认
# 120s，外层再包一层保证每轮必然收敛，不会挂死调度器
CALL_TIMEOUT = 150
# 每轮输出在报告中的截断长度（完整会话过长会撑爆 JSON 列与 PDF）
OUTPUT_LIMIT = 4000
# 多轮对话上限（产品口径：测试问题最多 10 个 = 10 轮连续对话）
MAX_TURNS = 10
# 交给判定模型的对话记录整体截断长度
JUDGE_TRANSCRIPT_LIMIT = 8000

JUDGE_RULE_TYPES = ("contains", "not_contains", "regex", "llm_judge")

DEFAULT_PROMPTS = ["你好，请用一句话介绍你自己"]


class _ProbeConn:
    """provider 运行时所需的最小连接替身（同 test/probe_hbh_llm.py）。

    openai.py 用 status 判断打断、rhn_workflow 写 current_language、
    notify_client_error 取 websocket（None 时静默跳过）。
    """
    status = WebsocketConnectionEvent.IDLE.value
    current_language = None
    websocket = None


def _truncate(text: str) -> str:
    if text and len(text) > OUTPUT_LIMIT:
        return text[:OUTPUT_LIMIT] + "…（已截断）"
    return text


def task_prompts(task) -> list:
    """取任务的多轮问题（兼容旧单轮 test_prompt；空则用默认问题）。"""
    prompts = [str(p).strip() for p in (task.test_prompts or []) if str(p or "").strip()]
    if not prompts and task.test_prompt:
        prompts = [task.test_prompt]
    return prompts or list(DEFAULT_PROMPTS)


async def _call_plugin(cfg: dict, prompts: list, session_id: str):
    """加载 provider 并在同一会话按序多轮对话。

    返回 (turns, error, seconds, first_token_s)：
      turns  = [{index, prompt, output, error, seconds}]（出错轮的后续轮
               不再继续，error 记在失败轮上）
      error  = 整体错误（首错即整体失败；全部轮无输出也算错误）

    session_id 必须每次运行唯一且全程一致：rhn_workflow 等工作流服务按
    session_id 维护会话上下文——唯一避免串上历史测试，一致才能让多轮
    问题成为真正的连续对话。
    """
    t0 = time.perf_counter()
    try:
        mod = importlib.import_module(f"utils.providers.llm.{cfg['type']}")
        engine = mod.LLMProvider(cfg)
    except Exception as e:
        return [], f"插件加载失败 {type(e).__name__}: {e}", round(time.perf_counter() - t0, 2), None

    conn = _ProbeConn()
    dialogue = []
    turns = []
    first_token = None
    error = None

    for idx, question in enumerate(prompts[:MAX_TURNS], start=1):
        dialogue.append({"role": "user", "content": question})
        turn_t0 = time.perf_counter()
        collected = ""

        async def _collect():
            nonlocal collected, first_token
            async for part in engine.response(session_id, list(dialogue), conn=conn):
                if part:
                    if first_token is None:
                        first_token = time.perf_counter() - t0
                    collected += part

        turn_error = None
        try:
            await asyncio.wait_for(_collect(), timeout=CALL_TIMEOUT)
        except asyncio.TimeoutError:
            turn_error = f"第{idx}轮调用超时（>{CALL_TIMEOUT}s）"
        except Exception as e:
            turn_error = f"第{idx}轮调用异常 {type(e).__name__}: {e}"
        if not turn_error and not collected.strip():
            turn_error = f"第{idx}轮无输出——服务无返回或返回格式未被解析"

        turns.append({"index": idx, "prompt": question,
                      "output": _truncate(collected) or None,
                      "error": turn_error,
                      "seconds": round(time.perf_counter() - turn_t0, 2)})
        if turn_error:
            error = turn_error
            break  # 会话已异常，继续追问只会产生误导性回答
        dialogue.append({"role": "assistant", "content": collected})

    if error is None and not any((t["output"] or "").strip() for t in turns):
        error = "无输出——服务无返回或返回格式未被解析"
    return turns, error, round(time.perf_counter() - t0, 2), \
        round(first_token, 2) if first_token else None


def full_output(turns: list) -> str:
    """各轮回复合并文本（关键字/正则规则的校验对象）。"""
    return "\n".join(t["output"] for t in turns if t.get("output")).strip()


def build_transcript(turns: list) -> str:
    """完整对话记录（判定模型的校验对象：逐轮问+答）。"""
    lines = []
    for t in turns:
        lines.append(f"第{t['index']}轮")
        lines.append(f"用户：{t['prompt']}")
        lines.append(f"助手：{t['output'] if t.get('output') else ('（调用失败：' + str(t.get('error')) + '）')}")
    text = "\n".join(lines)
    if len(text) > JUDGE_TRANSCRIPT_LIMIT:
        text = text[:JUDGE_TRANSCRIPT_LIMIT] + "…（已截断）"
    return text


# ---------------------------------------------------------------- 判定模型

def _judge_llm_config():
    """取 config.yaml THIRD_PARTY_SERVICES -> generic_llm -> Qwen3.8-fash-next。

    该配置项是列表嵌 dict（同 get_service 的访问方式），逐项探测。
    """
    for svc in config_data["THIRD_PARTY_SERVICES"]:
        generic = svc.get("generic_llm") if isinstance(svc, dict) else None
        if generic:
            conf = generic.get("Qwen3.8-fash-next")
            if conf:
                return conf
    raise KeyError("config.yaml THIRD_PARTY_SERVICES.generic_llm 缺少 Qwen3.8-fash-next")


JUDGE_SYSTEM = (
    "你是严格的 LLM 多轮对话质量评审员。给定「完整对话记录」（用户逐轮提问与"
    "助手逐轮回答）和「判定要求」，综合全部对话内容判断是否满足判定要求。\n"
    "输出格式（严格遵守）：\n"
    "第 1 行：只写 PASS 或 FAIL 一个词；\n"
    "第 2 行起：判定理由。判 FAIL 时理由必须充分：逐条指出哪些轮次的哪些原文"
    "片段不满足判定要求、为何不满足，并在合适时给出改进建议（改测试问题、改"
    "判定要求还是修被测插件）；判 PASS 时简要说明依据。理由须引用对话原文、"
    "具体可复核，不要空泛套话。"
)


def _pick_verdict(seg: str):
    """一段文本里取结论：同时出现时以最后出现的为准（结论通常在结尾）。"""
    last_pass, last_fail = seg.rfind("PASS"), seg.rfind("FAIL")
    if last_pass < 0 and last_fail < 0:
        return None
    return "PASS" if last_pass > last_fail else "FAIL"


def _parse_judge(text: str):
    """解析「首行结论 + 理由正文」。返回 (PASS|FAIL|None, 理由)。"""
    t = (text or "").strip()
    if not t:
        return None, ""
    lines = t.splitlines()
    verdict = _pick_verdict(lines[0].strip().upper()) or _pick_verdict(t.upper())
    reason = "\n".join(lines[1:]).strip() if verdict and len(lines) > 1 else t
    return verdict, reason


async def _judge_by_llm(transcript: str, requirement: str):
    """用 generic_llm 判定模型对整个对话记录校验。返回 (passed, detail)。

    判定模型（qwen3.8）走思考模式（enable_thinking=True）：思考过程在
    reasoning_content、结论+理由在 content，要求模型首行给 PASS/FAIL、
    正文给充分理由（FAIL 时须引用轮次原文说明为什么不满足）。思考链可能
    耗尽预算导致 content 为空，此时退回思维链尾部找结论。
    """
    conf = _judge_llm_config()
    client = openai.AsyncClient(
        api_key=conf.get("apikey"), base_url=conf.get("base_url"),
        timeout=httpx.Timeout(180))
    user = (f"【完整对话记录】\n{transcript}\n\n"
            f"【判定要求】\n{requirement}\n\n请按输出格式判定：")
    try:
        resp = await client.chat.completions.create(
            model=conf.get("model"),
            messages=[{"role": "system", "content": JUDGE_SYSTEM},
                      {"role": "user", "content": user}],
            # 思考模式开启：思考链 + 「结论+理由」正文都算输出，预算放大
            max_tokens=4096, temperature=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}})
        msg = resp.choices[0].message
        verdict, reason = _parse_judge(msg.content or "")
        if verdict is None:
            # 正文没有结论（思考预算耗尽等），退到思维链尾部
            reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
            verdict = _pick_verdict(reasoning.upper()) if reasoning else None
            reason = reasoning[-800:] if reasoning else (msg.content or "").strip()
        if verdict == "PASS":
            return True, f"判定模型判 PASS。理由：{reason[:500] or '（未给出）'}"
        if verdict == "FAIL":
            return False, f"判定模型判 FAIL。理由：{reason[:1200] or '（未给出）'}"
        return False, (f"判定模型返回无法解析（无 PASS/FAIL 结论）。"
                       f"原始返回摘录：{(reason or '（空）')[:400]}")
    except Exception as e:
        # 判定模型自身故障不冤枉被测插件：判 error（整体不算通过，但原因如实透出）
        return None, f"判定模型调用失败：{type(e).__name__}: {e}"


def _excerpt(text: str, n: int = 160) -> str:
    """把输出压成单行摘录（失败明细里给出「实际输出是什么」，便于复核）。"""
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if not t:
        return "（空）"
    return t[:n] + "…" if len(t) > n else t


def _hit_context(text: str, needle: str, pad: int = 40) -> str:
    """违禁片段命中处取一段上下文。"""
    i = (text or "").lower().find(str(needle or "").lower())
    if i < 0:
        return _excerpt(text)
    return _excerpt(text[max(0, i - pad):i + len(needle) + pad])


async def _check_rules(rules, transcript: str, output_text: str):
    """逐条执行规则，返回明细列表 [{type,value,passed,detail}]。

    contains/not_contains/regex 作用于所有轮次回复的合并文本 output_text；
    llm_judge 把完整对话记录 transcript（含逐轮提问）交给判定模型。
    """
    details = []
    low = (output_text or "").lower()
    for r in rules or []:
        rtype, value = (r or {}).get("type"), (r or {}).get("value")
        item = {"type": rtype, "value": value, "passed": False, "detail": ""}
        details.append(item)
        if rtype == "contains":
            ok = str(value or "").lower() in low
            item["passed"] = ok
            item["detail"] = ("对话输出包含" if ok else
                              f"全部对话输出未包含「{value}」；实际输出：{_excerpt(output_text)}")
        elif rtype == "not_contains":
            ok = str(value or "").lower() not in low
            item["passed"] = ok
            item["detail"] = ("对话输出未包含" if ok else
                              f"对话输出含违禁片段「{value}」；命中上下文：…{_hit_context(output_text, value)}…")
        elif rtype == "regex":
            try:
                ok = re.search(str(value or ""), output_text or "", re.S) is not None
                item["passed"] = ok
                item["detail"] = ("匹配" if ok else
                                  f"对话输出不匹配正则 {value}；实际输出：{_excerpt(output_text)}")
            except re.error as e:
                item["passed"] = False
                item["detail"] = f"正则表达式非法：{e}"
        elif rtype == "llm_judge":
            passed, detail = await _judge_by_llm(transcript, str(value or ""))
            item["passed"] = bool(passed)
            item["detail"] = detail
            if passed is None:
                item["error"] = True  # 判定模型故障，区别于插件真不合格
        else:
            item["passed"] = False
            item["detail"] = f"未知规则类型：{rtype}"
    return details


# ---------------------------------------------------------------- 运行入口

async def run_task(task_id: int, trigger: str = "manual"):
    """执行一个测试任务并把报告写回 PluginTestTask（调度器/手动运行共用）。

    任务级并发不需要并行——插件逐个跑，避免同一时刻打爆被测服务；
    返回报告 dict（同时已落库）。每次运行同时留档一条 PluginTestRun
    历史记录（全量保留，报告快照里回写 run_id 供查看/下载 PDF）。
    """
    from mybatisPlus.tables.industrial_park import PluginTestTask, PluginTestRun, beijing_now
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        task = await session.scalar(select(PluginTestTask).filter_by(id=task_id))
        if not task or task.is_delete:
            raise ValueError(f"测试任务 #{task_id} 不存在")
        name = task.name
        plugin_ids = list(task.plugin_ids or [])
        prompts = task_prompts(task)
        rules = list(task.rules or [])
        owner_id = task.owner_id

    items = []
    for pid in plugin_ids:
        async with AsyncSessionLocal() as session:
            try:
                cfg = await resolve_runtime_config(session, "LLM_CUSTOM", pid)
            except PluginUnavailableError as e:
                cfg = None
                plugin_name = f"#{pid}"
                items.append({"plugin_id": pid, "plugin_name": plugin_name,
                              "ok": False, "error": str(e), "turns": [], "checks": []})
                continue
        if cfg is None:
            items.append({"plugin_id": pid, "plugin_name": f"#{pid}",
                          "ok": False, "error": "插件不存在或已删除", "turns": [], "checks": []})
            continue
        plugin_name = cfg.get("name") or f"#{pid}"
        # 每次运行每个插件用全新 session_id：与上一次测试隔离，而任务内
        # 各轮共用它，形成真正的连续对话
        turns, error, seconds, first_token = await _call_plugin(
            cfg, prompts, session_id=f"llm-test-{task_id}-{uuid.uuid4().hex[:8]}")
        output_text = full_output(turns)
        item = {"plugin_id": pid, "plugin_name": plugin_name,
                "base_plugin": cfg.get("type"), "url": cfg.get("url"),
                "turns": turns, "output": _truncate(output_text) or None,
                "error": error,
                "seconds": seconds, "first_token_seconds": first_token,
                "checks": []}
        if error:
            item["ok"] = False
        else:
            item["checks"] = await _check_rules(
                rules, build_transcript(turns), output_text)
            item["ok"] = all(c["passed"] for c in item["checks"])
        items.append(item)
        scheduled_task_logger.info(
            f"LLM自动化测试 任务#{task_id} 插件#{pid}（{plugin_name}）"
            f"{len(turns)}轮 → {'通过' if item['ok'] else '失败'} {seconds}s"
            + (f"：{error}" if error else ""))

    ok_cnt = sum(1 for i in items if i["ok"])
    run_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    report = {
        "task_id": task_id, "task_name": name, "trigger": trigger,
        "run_time": run_time,
        "prompts": prompts,
        "rules": rules,
        "items": items,
        "summary": {"total": len(items), "ok": ok_cnt, "fail": len(items) - ok_cnt},
    }

    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        # 历史留档：先插入 PluginTestRun 拿到 run_id，回写进报告快照后再
        # 同步给任务 last_report——两份报告内容一致且都带 run_id，前端
        # 按 run_id 走历史查看/PDF 下载，最新一次仍可从任务上直接拿。
        run = PluginTestRun(task_id=task_id, task_name=name, trigger=trigger,
                            run_time=beijing_now(), summary=report["summary"],
                            report=None, owner_id=owner_id)
        session.add(run)
        await session.flush()
        report["run_id"] = run.id
        run.report = report
        await session.execute(
            update(PluginTestTask).where(PluginTestTask.id == task_id).values(
                last_run_time=beijing_now(), last_trigger=trigger,
                last_summary=report["summary"], last_report=report))
        await session.commit()
    return report
