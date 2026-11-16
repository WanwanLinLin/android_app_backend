"""LLM 自动化测试定时调度器（每天重复运行）。

随应用启动一个后台 asyncio 循环（uvicorn 事件循环内，无额外线程）：
周期扫描 PluginTestTask 中「已启用定时、状态 pending、时间已到」的任务，
原子领取（pending→running，见 plugin_test_orm.claim_due_tasks，防并发
双跑）后执行 run_task，完成即把 schedule_time 顺延一天回到 pending
（plugin_test_orm.reschedule_task），实现每天同一时刻自动运行。

扫描间隔默认 20s（定时精度要求不高）。任务体内异常全部捕获落日志，
循环永不因单任务失败而退出（失败同样顺延到明天，不因一次失败卡死）。
服务重启时残留 running 行保持原样（不回滚、不自动补跑——避免重启风暴
重复调用外部服务），由用户在后台改时间重新排队。

日志统一走 utils.getLogs.scheduled_task_logger。
"""
import asyncio

from utils.getLogs import scheduled_task_logger
from mybatisPlus.tables.industrial_park import beijing_now

SCAN_INTERVAL = 20

_task_handle = None


async def _loop():
    # 延迟导入：避免 run.py 导入链上 mybatisPlus ↔ utils 相互引用放大
    from mybatisPlus.plugin_test_orm import claim_due_tasks, reschedule_task
    from utils.plugin_test.runner import run_task

    while True:
        try:
            claimed = await claim_due_tasks(beijing_now())
            for tid in claimed:
                scheduled_task_logger.info(f"LLM自动化测试 每日定时任务 #{tid} 开始运行")
                try:
                    await run_task(tid, trigger="scheduled")
                    scheduled_task_logger.info(f"LLM自动化测试 每日定时任务 #{tid} 运行完成，顺延至次日")
                except Exception as e:
                    scheduled_task_logger.error(f"LLM自动化测试 每日定时任务 #{tid} 运行失败: {e}")
                finally:
                    await reschedule_task(tid)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            scheduled_task_logger.error(f"LLM自动化测试调度器扫描异常: {e}")
        await asyncio.sleep(SCAN_INTERVAL)


def start_scheduler():
    """应用 startup 时调用：在事件循环内拉起后台扫描协程（幂等）。"""
    global _task_handle
    if _task_handle is None or _task_handle.done():
        _task_handle = asyncio.create_task(_loop())
        scheduled_task_logger.info("LLM自动化测试定时调度器已启动（每日重复模式）")
