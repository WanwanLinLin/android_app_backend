from fastapi.staticfiles import StaticFiles

import traceback
from fastapi.responses import JSONResponse
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from setting import config_data
from threading import Thread
from modules.user.views import router as user_router
from modules.tts.views import router as tts_router
from modules.llm.views import router as llm_router
from modules.asr.views import router as asr_router
from modules.stream.views import router as stream_router
from modules.video.views import router as video_router
from modules.figure.views import router as figure_router
from modules.chat_template.views import router as chat_template_router
from modules.session.views import router as session_router
from utils.apierror import AdminRequiredError, JwtAuthError

app = FastAPI(title="数字人对话通用接口文档", docs_url="/digitalhuman/api/v1")

app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(user_router)
app.include_router(tts_router)
app.include_router(llm_router)
app.include_router(asr_router)
app.include_router(stream_router)
app.include_router(video_router)
app.include_router(figure_router)
app.include_router(chat_template_router)
app.include_router(session_router)


@app.exception_handler(JwtAuthError)
async def jwt_auth_exception_handler(request, exc: Exception):
    return JSONResponse(
            status_code=200,
            content={"code": 401, "msg": "Not authenticated", "data": None}
        )


@app.exception_handler(AdminRequiredError)
async def admin_required_exception_handler(request, exc: Exception):
    """资源池写操作要求 role=admin，非管理员账号触发时返回 403。"""
    return JSONResponse(
            status_code=200,
            content={"code": 403, "msg": "需要管理员权限", "data": None}
        )


# 处理所有异常
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    tb_str = traceback.format_exc()
    return JSONResponse(
        status_code=200,
        content={"code": 500, "msg": f"Internal Server Error: {str(exc)}, {tb_str[-150:]}", "data": None}
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config_data["SERVICES"][0]["port"])