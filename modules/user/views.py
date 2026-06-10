from fastapi import APIRouter, status
from utils.common.schema import GeneticResponse
from mybatisPlus.task_orm import create_task
from mybatisPlus.engineer_orm import list_engineers_detail
from utils.randomString import create_numbering

router = APIRouter(responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}})


@router.get("/v1/user/engineer/list")
async def _list_engineers():
    return GeneticResponse(data=await list_engineers_detail())