"""LLM 自动化测试任务数据访问层。

归属口径与个性插件一致（严格私有）：owner_id 恒为创建者本人，仅本人
可改/删/运行/下载；admin 列表可见全部（治理用途），但不代改别人的任务。
校验规则/插件列表/多轮问题的合法性在写入口做（规则类型、插件存在与
类别、问题数量上限）。
"""
from datetime import datetime, timedelta
from typing import List, Union

from sqlalchemy import func, or_, select, update

from utils.common.schema import GeneticResponse
from utils.plugin_test.runner import JUDGE_RULE_TYPES, MAX_TURNS
from .tables.industrial_park import CustomPlugin, PluginTestRun, PluginTestTask, beijing_now
from .tables.sqlcli import AsyncSessionLocal


def _alive(m):
    return or_(m.is_delete.is_(None), m.is_delete.is_(False))


def _serialize(t: PluginTestTask, mine: bool = True) -> dict:
    return {"id": t.id, "name": t.name, "desc": t.desc,
            "plugin_ids": t.plugin_ids or [],
            "test_prompts": _prompts_of(t),
            "rules": t.rules or [],
            "schedule_enabled": bool(t.schedule_enabled),
            "schedule_time": t.schedule_time.strftime("%Y-%m-%d %H:%M:%S") if t.schedule_time else None,
            "schedule_status": t.schedule_status,
            # 存量行可能在加列前为 NULL，视为开启（与建表默认一致）
            "notify_dingtalk": t.notify_dingtalk is not False,
            "last_run_time": t.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if t.last_run_time else None,
            "last_trigger": t.last_trigger, "last_summary": t.last_summary,
            "owner_id": t.owner_id,
            # 完整报告只在 get 详情返回（列表带全量 JSON 太重）
            "last_report": (t.last_report if mine else None)}


def _prompts_of(t: PluginTestTask) -> list:
    """统一取多轮问题；旧任务只有 test_prompt 时转成单元素列表。"""
    prompts = [p for p in (t.test_prompts or []) if str(p or "").strip()]
    if not prompts and t.test_prompt:
        prompts = [t.test_prompt]
    return prompts


def _validate_prompts(prompts) -> Union[list, tuple]:
    """归一化多轮问题：返回 list（通过）或 (None, err)（拒绝）。

    允许为空——runner 有默认问题；非空时最多 MAX_TURNS 条、每条非空。
    """
    if prompts in (None, []):
        return []
    if not isinstance(prompts, list):
        return None, "test_prompts 必须是数组"
    cleaned = []
    for p in prompts:
        p = str(p or "").strip()
        if not p:
            return None, "测试问题不能为空行"
        cleaned.append(p)
    if len(cleaned) > MAX_TURNS:
        return None, f"测试问题最多 {MAX_TURNS} 个（{MAX_TURNS} 轮连续对话），当前 {len(cleaned)} 个"
    return cleaned


def _validate_rules(rules) -> Union[str, None]:
    """规则结构校验：[{type in JUDGE_RULE_TYPES, value 非空字符串}]。"""
    if rules in (None, []):
        return None
    if not isinstance(rules, list):
        return "rules 必须是数组"
    for r in rules:
        if not isinstance(r, dict):
            return "每条规则必须是 {type, value} 对象"
        if r.get("type") not in JUDGE_RULE_TYPES:
            return f"规则类型必须是 {' | '.join(JUDGE_RULE_TYPES)}，收到：{r.get('type')}"
        if not str(r.get("value") or "").strip():
            return "规则内容（value）不能为空"
    return None


async def _validate_plugin_ids(plugin_ids) -> Union[str, None]:
    """所选插件必须全部是存在、未删除的 LLM 个性插件。"""
    if not plugin_ids or not isinstance(plugin_ids, list):
        return "请至少选择一个 LLM 个性插件"
    async with AsyncSessionLocal() as session:
        rows = set((await session.scalars(
            select(CustomPlugin.id).where(CustomPlugin.id.in_(plugin_ids),
                                          CustomPlugin.category == "LLM",
                                          _alive(CustomPlugin)))).all())
    missing = [i for i in plugin_ids if i not in rows]
    if missing:
        return f"插件不存在或不是 LLM 类别：{'、'.join(str(m) for m in missing)}"
    return None


async def get_task_list(admin: bool, user_id: int):
    """任务列表（轻量，不含完整报告）。严格私有：普通用户仅见自己的；admin 见全部。"""
    async with AsyncSessionLocal() as session:
        stmt = select(PluginTestTask).where(_alive(PluginTestTask))
        if not admin:
            stmt = stmt.where(PluginTestTask.owner_id == user_id)
        rows = (await session.scalars(stmt.order_by(PluginTestTask.id.desc()))).all()
        result = [_serialize(t, mine=(t.owner_id == user_id)) for t in rows]
        return {"rows": result, "total": len(result)}


async def get_one_task(id: int, admin: bool, user_id: int):
    """任务详情（含最近一次完整报告）。返回 (dict|None, 拒绝msg|None)。"""
    async with AsyncSessionLocal() as session:
        t = await session.scalar(select(PluginTestTask).filter_by(id=id))
        if not t or t.is_delete:
            return None, "data not exist"
        if t.owner_id != user_id and not admin:
            return None, "无权查看该任务"
        return _serialize(t), None


def _schedule_fields(kwargs, old_enabled=False, old_time=None, old_status=None):
    """归一化调度字段，返回 (enabled, time, status, err)。

    定时为「每天重复」：首次开启必须给未来的计划时间；之后每次运行完成
    由调度器把 schedule_time 顺延一天回到 pending（见 reschedule_task）。
    关闭定时 → canceled（调度器不再领取）。
    """
    enabled = bool(kwargs.get("schedule_enabled", old_enabled))
    stime = kwargs.get("schedule_time")
    if stime and isinstance(stime, str):
        stime = datetime.strptime(stime.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
    if not enabled:
        # 关闭定时：清空计划字段，排队/已跑过的一律 canceled
        return False, None, ("canceled" if (old_enabled or old_status) else None), None
    if not stime:
        return None, None, None, "启用定时运行必须选择每天运行时间"
    # schedule_time 落库为 naive 北京时间；beijing_now() 带 tzinfo=utc 标记，
    # 直接比较会抛 naive/aware TypeError，统一去 tzinfo 再比。
    if stime <= beijing_now().replace(tzinfo=None, microsecond=0):
        return None, None, None, "首次运行时间必须晚于当前时间"
    # 时间被改（或新开启/曾关闭再开启）→ 重新排队
    status = "pending" if (stime != old_time or not old_enabled
                           or old_status in ("canceled", "done")) else old_status
    return True, stime, status, None


async def create_task(user_id: int, **kwargs):
    err = await _validate_plugin_ids(kwargs.get("plugin_ids"))
    if err:
        return GeneticResponse(code=400, msg=err)
    err = _validate_rules(kwargs.get("rules"))
    if err:
        return GeneticResponse(code=400, msg=err)
    prompts = _validate_prompts(kwargs.get("test_prompts"))
    if isinstance(prompts, tuple):
        return GeneticResponse(code=400, msg=prompts[1])
    enabled, stime, status, err = _schedule_fields(kwargs)
    if err:
        return GeneticResponse(code=400, msg=err)
    name = (kwargs.get("name") or "").strip()
    if not name:
        return GeneticResponse(code=400, msg="任务名称不能为空")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            t = PluginTestTask(name=name, desc=kwargs.get("desc"),
                               plugin_ids=kwargs.get("plugin_ids"),
                               test_prompts=prompts or None,
                               rules=kwargs.get("rules") or [],
                               schedule_enabled=enabled, schedule_time=stime,
                               schedule_status=status,
                               # 新建默认开启钉钉播报（仅定时运行结果会播）
                               notify_dingtalk=kwargs.get("notify_dingtalk") is not False,
                               owner_id=user_id,
                               is_delete=False)
            session.add(t)
            await session.flush()
            return GeneticResponse(data={"id": t.id})


async def update_task(id: int, admin: bool, user_id: int, **kwargs):
    """更新任务。严格私有：仅创建者本人可改（admin 不代改别人的）。"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            t = await session.scalar(select(PluginTestTask).filter_by(id=id))
            if not t or t.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            if t.owner_id != user_id:
                return GeneticResponse(code=403, msg="只能修改自己创建的测试任务")
            if t.schedule_status == "running":
                return GeneticResponse(code=400, msg="定时任务正在运行中，稍后再改")
            if "plugin_ids" in kwargs:
                err = await _validate_plugin_ids(kwargs.get("plugin_ids"))
                if err:
                    return GeneticResponse(code=400, msg=err)
            if "rules" in kwargs:
                err = _validate_rules(kwargs.get("rules"))
                if err:
                    return GeneticResponse(code=400, msg=err)
            if "test_prompts" in kwargs:
                prompts = _validate_prompts(kwargs.get("test_prompts"))
                if isinstance(prompts, tuple):
                    return GeneticResponse(code=400, msg=prompts[1])
                kwargs["test_prompts"] = prompts or None
                # 切到多轮后清掉旧单轮字段，避免 _prompts_of 回退到旧值
                kwargs["test_prompt"] = None
            enabled, stime, status, err = _schedule_fields(
                kwargs, old_enabled=bool(t.schedule_enabled),
                old_time=t.schedule_time, old_status=t.schedule_status)
            if err:
                return GeneticResponse(code=400, msg=err)
            for k in ("name", "desc", "plugin_ids", "test_prompts", "test_prompt", "rules",
                      "notify_dingtalk"):
                if k in kwargs:
                    setattr(t, k, kwargs[k])
            t.schedule_enabled, t.schedule_time, t.schedule_status = enabled, stime, status
            session.add(t)
            return GeneticResponse()


async def delete_task(id: int, admin: bool, user_id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            t = await session.scalar(select(PluginTestTask).filter_by(id=id))
            if not t or t.is_delete:
                return GeneticResponse(code=400, msg="data not exist")
            if t.owner_id != user_id:
                return GeneticResponse(code=403, msg="只能删除自己创建的测试任务")
            t.is_delete = True
            session.add(t)
            return GeneticResponse()


async def claim_due_tasks(now):
    """调度器用：把「到期的 pending」原子领取为 running，返回任务 id 列表。

    先查候选（隐式事务），commit 结束后再对每个 id 做条件 UPDATE
    （WHERE schedule_status='pending'）认领——rowcount=1 才算抢到，天然
    防并发双跑；单/多实例都安全。now 归一为 naive（列为 naive 北京时间）。
    """
    now = now.replace(tzinfo=None) if now.tzinfo else now
    async with AsyncSessionLocal() as session:
        cands = (await session.scalars(
            select(PluginTestTask.id).where(
                _alive(PluginTestTask),
                PluginTestTask.schedule_enabled.is_(True),
                PluginTestTask.schedule_status == "pending",
                PluginTestTask.schedule_time <= now))).all()
        if not cands:
            return []
        await session.commit()  # 结束候选查询的隐式事务，下面 begin 才不冲突
        claimed = []
        async with session.begin():
            for tid in cands:
                r = await session.execute(
                    update(PluginTestTask)
                    .where(PluginTestTask.id == tid,
                           PluginTestTask.schedule_status == "pending")
                    .values(schedule_status="running"))
                if r.rowcount:
                    claimed.append(tid)
        return claimed


def _run_serialize(r: PluginTestRun, full: bool = False) -> dict:
    """历史记录序列化；列表默认轻量（不带 report 全量 JSON）。"""
    d = {"id": r.id, "task_id": r.task_id, "task_name": r.task_name,
         "trigger": r.trigger,
         "run_time": r.run_time.strftime("%Y-%m-%d %H:%M:%S") if r.run_time else None,
         "summary": r.summary}
    if full:
        d["report"] = r.report
    return d


async def list_task_runs(task_id: int, admin: bool, user_id: int,
                         limit: int = 50, offset: int = 0):
    """某任务的历史运行列表（时间倒序，轻量）。返回 (dict|None, 拒绝msg|None)。

    任务本身无权/不存在时直接拒绝——历史记录权限随任务（严格私有，
    admin 可见全部）。
    """
    async with AsyncSessionLocal() as session:
        t = await session.scalar(select(PluginTestTask).filter_by(id=task_id))
        if not t or t.is_delete:
            return None, "data not exist"
        if t.owner_id != user_id and not admin:
            return None, "无权查看该任务"
        total = await session.scalar(
            select(func.count()).select_from(PluginTestRun)
            .where(PluginTestRun.task_id == task_id)) or 0
        rows = (await session.scalars(
            select(PluginTestRun).where(PluginTestRun.task_id == task_id)
            .order_by(PluginTestRun.run_time.desc(), PluginTestRun.id.desc())
            .offset(offset).limit(limit))).all()
        return {"rows": [_run_serialize(r) for r in rows], "total": total}, None


async def get_run(run_id: int, admin: bool, user_id: int):
    """单条历史运行详情（含完整报告快照）。返回 (dict|None, 拒绝msg|None)。"""
    async with AsyncSessionLocal() as session:
        r = await session.scalar(select(PluginTestRun).filter_by(id=run_id))
        if not r:
            return None, "data not exist"
        t = await session.scalar(select(PluginTestTask).filter_by(id=r.task_id))
        owner = (t.owner_id if t else r.owner_id)
        if owner != user_id and not admin:
            return None, "无权查看该记录"
        return _run_serialize(r, full=True), None


async def get_task_notify_info(id: int):
    """钉钉异常告警用：取 (任务名, 任务描述, 是否播报)。不存在返回 (None, None, None)。

    与 get_one_task 不同——不做权限判断（后台调度器内部使用），存量行
    notify_dingtalk 为 NULL 视为开启。多列查询必须用 execute().first() 取
    Row：session.scalar() 会把结果降为首列标量（字符串），届时 t[0] 只是
    任务名的第一个字符，开关判断会永远为真。
    """
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(PluginTestTask.name, PluginTestTask.desc, PluginTestTask.notify_dingtalk)
            .where(PluginTestTask.id == id))).first()
        if not row:
            return None, None, None
        return row[0], row[1], row[2] is not False


async def reschedule_task(id: int):
    """定时（每天重复）任务运行结束：schedule_time 顺延一天回到 pending。

    以「原计划时间 + 1 天」为基准顺延，保持每天同一时刻运行；若顺延后
    仍早于当前（服务长时间停机等极端情况），则一路 +1 天直到未来，避免
    下一轮扫描立刻重复领取。若任务在运行期间被改名/改时间（stime 已变）
    或关闭定时，则由调度器写入的旧值被用户覆盖——这里只处理仍处 running
    且未被关闭的行。
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            t = await session.scalar(select(PluginTestTask).filter_by(id=id))
            if not t or not t.schedule_enabled:
                return
            base = t.schedule_time or beijing_now().replace(tzinfo=None)
            if base.tzinfo:
                base = base.replace(tzinfo=None)
            nxt = base + timedelta(days=1)
            now = beijing_now().replace(tzinfo=None)
            while nxt <= now:
                nxt += timedelta(days=1)
            await session.execute(
                update(PluginTestTask).where(PluginTestTask.id == id).values(
                    schedule_time=nxt, schedule_status="pending"))
