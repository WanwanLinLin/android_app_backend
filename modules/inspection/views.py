# -*- coding：utf-8 -*-
from . import schema
from fastapi import APIRouter, File, Form, UploadFile, status
from utils.common.schema import GeneticResponse
from utils.randomString import create_numbering
from setting import config_data
from mybatisPlus.work_order_inspection_orm import (wo_get_inspection_info_by_task_id, wo_get_nfc_info,
                                                   wo_get_all_unstart_tasks, wo_start_inspection_task,
                                                   wo_check_in_inspection_task)

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.get("/v1/inspection/getNfcInfo")
async def _get_nfc_info():
    
    return GeneticResponse(data=await wo_get_nfc_info())


@router.post("/v1/inspection/start")
async def _start(info: schema.StartModel):
    if not (await wo_start_inspection_task(info.task_id, info.device_id)):
        return GeneticResponse(code=400, msg="任务不存在。")
    return GeneticResponse()


@router.post("/v1/inspection/info")
async def _info(info: schema.InfoModel):
    return GeneticResponse(data=await wo_get_inspection_info_by_task_id(info.task_id))


@router.post("/v1/inspection/checkIn")
async def _check_in(info: schema.CheckInModel):
    if not (await wo_check_in_inspection_task(info.task_id, info.nfc_code, info.device_id)):
        return GeneticResponse(code=400, msg="任务不存在。")
    return GeneticResponse()