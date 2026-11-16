import urllib.parse

from . import schema
from fastapi import APIRouter, BackgroundTasks, status, Depends
from fastapi.responses import Response

from utils.common.schema import GeneticResponse
from utils.admin_auth import current_admin, is_admin
from mybatisPlus.plugin_test_orm import (get_task_list, get_one_task, create_task,
                                         update_task, delete_task,
                                         list_task_runs, get_run)

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


# LLM 自动化测试：对选定的 LLM 个性插件批量真实调用（每个插件在同一会话
# 里按序多轮提问，最多 10 轮），按自定义规则校验全部对话内容，结果存任务
# 上、可导出 PDF；定时为每天重复运行（调度器见 utils/plugin_test）。
# 归属严格私有（与个性插件一致）：仅创建者可改/删/运行/下载，admin 列表可见全部。

@router.get("/v1/llmTest/task/list", summary="测试任务列表", tags=["通用接口"])
async def _list_tasks(admin: dict = Depends(current_admin)):
    return GeneticResponse(data=await get_task_list(is_admin(admin), admin["id"]))


@router.get("/v1/llmTest/task/get/{id}", summary="测试任务详情（含最近报告）", tags=["通用接口"])
async def _get_task(id: int, admin: dict = Depends(current_admin)):
    data, err = await get_one_task(id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该任务" else 400, msg=err)
    return GeneticResponse(data=data)


@router.post("/v1/llmTest/task/add", summary="创建测试任务", tags=["通用接口"])
async def _add_task(info: schema.AddLlmTestTaskModel, admin: dict = Depends(current_admin)):
    payload = info.model_dump(exclude_none=True)
    if "rules" in payload:
        payload["rules"] = [r if isinstance(r, dict) else r.model_dump() for r in payload["rules"]]
    return await create_task(admin["id"], **payload)


@router.post("/v1/llmTest/task/update/{id}", summary="更新测试任务（仅创建者）", tags=["通用接口"])
async def _update_task(id: int, info: schema.UpdateLlmTestTaskModel,
                       admin: dict = Depends(current_admin)):
    payload = info.model_dump(exclude_none=True)
    if "rules" in payload:
        payload["rules"] = [r if isinstance(r, dict) else r.model_dump() for r in payload["rules"]]
    return await update_task(id, is_admin(admin), admin["id"], **payload)


@router.post("/v1/llmTest/task/delete/{id}", summary="删除测试任务（仅创建者）", tags=["通用接口"])
async def _delete_task(id: int, admin: dict = Depends(current_admin)):
    return await delete_task(id, is_admin(admin), admin["id"])


# 同任务并发防重：正在运行时再次点击直接拒绝（进程内即可，调度器领取走 DB 原子状态）
_running: set = set()


@router.post("/v1/llmTest/task/run/{id}", summary="立即运行测试任务", tags=["通用接口"])
async def _run_task(id: int, background: BackgroundTasks, admin: dict = Depends(current_admin)):
    """同步执行（逐个插件真实调用），返回完整报告。

    多插件耗时可达分钟级，前端此接口单独放大超时；任务级互斥防双击并发。
    """
    data, err = await get_one_task(id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该任务" else 400, msg=err)
    if id in _running:
        return GeneticResponse(code=400, msg="该任务正在运行中，请等待本次完成")
    from utils.plugin_test.runner import run_task
    _running.add(id)
    try:
        report = await run_task(id, trigger="manual")
    except Exception as e:
        return GeneticResponse(code=500, msg=f"运行失败：{e}")
    finally:
        _running.discard(id)
    return GeneticResponse(data=report)


@router.post("/v1/llmTest/task/runAsync/{id}", summary="后台运行测试任务（不等待结果）", tags=["通用接口"])
async def _run_task_async(id: int, background: BackgroundTasks, admin: dict = Depends(current_admin)):
    """大插件量场景：提交后台执行，前端轮询 task/get 取结果。"""
    data, err = await get_one_task(id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该任务" else 400, msg=err)
    if id in _running:
        return GeneticResponse(code=400, msg="该任务正在运行中，请等待本次完成")
    from utils.plugin_test.runner import run_task

    async def _wrap():
        _running.add(id)
        try:
            await run_task(id, trigger="manual")
        except Exception as e:
            from utils.getLogs import scheduled_task_logger
            scheduled_task_logger.error(f"LLM自动化测试 后台运行任务#{id}失败: {e}")
        finally:
            _running.discard(id)

    background.add_task(_wrap)
    return GeneticResponse(msg="已提交后台运行")


# 一键测试：把当前用户可见的全部测试任务【后台】运行，最多同时
# BATCH_CONCURRENCY 个并发、其余排队（信号量按提交顺序 FIFO 排队）。
# 单进程内存态记进度，前端轮询 status 展示 x/y 与正在运行的任务名；
# 与单任务运行、定时运行共用 _running 互斥。
BATCH_CONCURRENCY = 5
_batch: dict = {"running": False, "total": 0, "done": 0, "ok": 0, "fail": 0,
                "skipped": 0, "current": None, "current_list": [],
                "concurrency": BATCH_CONCURRENCY}


@router.post("/v1/llmTest/task/runAll", summary="一键运行全部测试任务（后台，最多5并发）", tags=["通用接口"])
async def _run_all_tasks(background: BackgroundTasks, admin: dict = Depends(current_admin)):
    if _batch["running"]:
        return GeneticResponse(code=400, msg="一键测试批次正在运行中，请等待本批完成")
    is_adm = is_admin(admin)
    data = await get_task_list(is_adm, admin["id"])
    # 可见即可运行（admin 可跑别人的，与单任务 run 口径一致）；提交时已被
    # 手动/定时占用的直接跳过，不占排队名额
    targets, skipped = [], 0
    for r in data["rows"]:
        if r["id"] in _running or r.get("schedule_status") == "running":
            skipped += 1
        else:
            targets.append((r["id"], r["name"]))
    if not targets:
        return GeneticResponse(code=400, msg="没有可运行的测试任务（不存在或全部正在运行中）")
    from utils.plugin_test.runner import run_task
    from utils.getLogs import scheduled_task_logger
    import asyncio

    # 先置位再提交：接口返回到后台任务启动之间不允许第二个批次插入
    # （事件循环内 check-and-set 无 await，天然原子）
    _batch.update({"running": True, "total": len(targets), "done": 0, "ok": 0,
                   "fail": 0, "skipped": skipped, "current": None, "current_list": []})

    async def _wrap():
        sem = asyncio.Semaphore(BATCH_CONCURRENCY)
        current = set()  # 正在运行的任务名（<= concurrency 个）

        def _sync_current():
            _batch["current_list"] = sorted(current)
            _batch["current"] = "、".join(_batch["current_list"]) or None

        async def _one(tid, tname):
            async with sem:
                if tid in _running:  # 排队期间被单点/定时占用的，跳过
                    _batch["skipped"] += 1
                    _batch["done"] += 1
                    return
                _running.add(tid)
                current.add(tname)
                _sync_current()
                try:
                    report = await run_task(tid, trigger="manual")
                    summary = report.get("summary") or {}
                    _batch["ok" if not summary.get("fail") else "fail"] += 1
                except Exception as e:
                    _batch["fail"] += 1
                    scheduled_task_logger.error(f"LLM自动化测试 一键运行任务#{tid}失败: {e}")
                finally:
                    current.discard(tname)
                    _running.discard(tid)
                    _batch["done"] += 1
                    _sync_current()

        try:
            await asyncio.gather(*(_one(tid, tname) for tid, tname in targets))
        finally:
            _batch["running"] = False

    background.add_task(_wrap)
    queued = max(len(targets) - BATCH_CONCURRENCY, 0)
    return GeneticResponse(data={"total": len(targets), "skipped": skipped,
                                 "concurrency": BATCH_CONCURRENCY, "queued": queued},
                           msg=(f"已提交 {len(targets)} 个任务后台运行"
                                f"（最多 {BATCH_CONCURRENCY} 个并发"
                                + (f"，{queued} 个排队" if queued else "") + "）"))


@router.get("/v1/llmTest/runAll/status", summary="一键测试批次进度", tags=["通用接口"])
async def _run_all_status(admin: dict = Depends(current_admin)):
    return GeneticResponse(data=dict(_batch))


@router.get("/v1/llmTest/task/report/{id}/pdf", summary="下载最近一次测试报告（PDF）", tags=["通用接口"])
async def _report_pdf(id: int, admin: dict = Depends(current_admin)):
    data, err = await get_one_task(id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该任务" else 400, msg=err)
    report = data.get("last_report")
    if not report:
        return GeneticResponse(code=400, msg="该任务还没有测试结果，请先运行")
    from utils.plugin_test.pdf import build_report_pdf
    try:
        pdf_bytes = build_report_pdf(report)
    except RuntimeError as e:
        return GeneticResponse(code=500, msg=str(e))
    fname = urllib.parse.quote(f"LLM测试报告_{data['name']}_{report.get('run_time') or ''}.pdf")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})


# ===================== 历史测试记录 =====================
# 每次运行（手动/定时）留档一条 PluginTestRun，全量保留；权限随任务：
# 严格私有的历史仅创建者可见，admin 可见全部（治理用途）。

@router.get("/v1/llmTest/task/runs/{id}", summary="任务历史运行记录列表", tags=["通用接口"])
async def _task_runs(id: int, limit: int = 50, offset: int = 0,
                     admin: dict = Depends(current_admin)):
    data, err = await list_task_runs(id, is_admin(admin), admin["id"],
                                     limit=min(max(limit, 1), 200), offset=max(offset, 0))
    if err:
        return GeneticResponse(code=403 if err == "无权查看该任务" else 400, msg=err)
    return GeneticResponse(data=data)


@router.get("/v1/llmTest/run/get/{run_id}", summary="历史运行详情（含完整报告）", tags=["通用接口"])
async def _get_run(run_id: int, admin: dict = Depends(current_admin)):
    data, err = await get_run(run_id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该记录" else 400, msg=err)
    return GeneticResponse(data=data)


@router.get("/v1/llmTest/run/{run_id}/pdf", summary="下载指定历史运行的报告（PDF）", tags=["通用接口"])
async def _run_pdf(run_id: int, admin: dict = Depends(current_admin)):
    data, err = await get_run(run_id, is_admin(admin), admin["id"])
    if err:
        return GeneticResponse(code=403 if err == "无权查看该记录" else 400, msg=err)
    report = data.get("report")
    if not report:
        return GeneticResponse(code=400, msg="该历史记录缺少报告内容")
    from utils.plugin_test.pdf import build_report_pdf
    try:
        pdf_bytes = build_report_pdf(report)
    except RuntimeError as e:
        return GeneticResponse(code=500, msg=str(e))
    fname = urllib.parse.quote(
        f"LLM测试报告_{data.get('task_name') or data['task_id']}_{data.get('run_time') or ''}.pdf")
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})
