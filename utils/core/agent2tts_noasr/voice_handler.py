import json
import time
import asyncio
from fastapi import WebSocket

from utils.getLogs import LOG
from utils.common.enumTaskType import WebsocketServerEvent, WebsocketClientEvent, ServerInternalEvent, WebsocketConnectionEvent
# 连接态对象沿用 webrtc_aec3 模板的定义：stream/views.py 统一以该类建连，
# 各模板只负责编排处理逻辑，不各自另立连接状态类。
from utils.core.webrtc_aec3.voice_handler import ConnectionObjectCustomAec3


# ============================================================
# 客户端 ASR 对话模板（agent -> tts，服务端不做语音识别）
# ------------------------------------------------------------
# 与 utils.core.webrtc_aec3.voice_handler 的唯一差异：语音识别由客户端完成。
# 客户端不再上行麦克风音频，而是上行识别完成的整句文本：
#     {"type": "transcription", "text": "今天天气怎么样", "language": "Chinese"}
# 服务端拿到后直接投递 conn.llm_queue，其余（LLM 流式生成、按标点切句、
# TTS 逐句合成与 Opus 下行、打断丢弃在途语音）与 webrtc_aec3 模板一致。
# ============================================================


async def receive_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Receive client messages. 本模板只处理文本帧：wakeup 打断、transcription 识别结果。

    二进制音频帧在本模板下不参与识别，若客户端仍推音频则直接忽略，
    避免 audio_chunk_queue 无消费者而无界增长。
    """
    while conn.is_active:
        message = await websocket.receive()
        if message["type"] == "websocket.receive":
            if "text" in message:
                command = json.loads(message["text"])
                LOG(f"收到客户端指令消息：{command}", "DEBUG")
                if command["type"] == WebsocketClientEvent.WAKEUP.value:
                    conn.status = WebsocketConnectionEvent.TALKING.value
                    await websocket.send_json({"type": WebsocketServerEvent.INTERRUPT.value})
                elif command["type"] == WebsocketClientEvent.TRANSCRIPTION.value:
                    text = command.get("text") or ""
                    language = command.get("language") or ""
                    LOG(f"客户端语音识别结果: {text}", "DEBUG")
                    # 整句识别完成 = 本轮说话结束：恢复 IDLE 让 TTS 音频可下行，
                    # 语义等同 webrtc_aec3 模板里 VAD 判尾后的 stop_listening。
                    conn.status = WebsocketConnectionEvent.IDLE.value
                    await websocket.send_json({"type": WebsocketServerEvent.STOP_LISTENING.value})
                    await websocket.send_json({"type": WebsocketServerEvent.TRANSCRIPTION.value, "text": text, "language": language})
                    if text: conn.llm_queue.put(text)
            elif "bytes" in message:
                ...


async def send_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Send TTS/playback audio to client, same as webrtc_aec3 template."""
    while conn.is_active:
        if not conn.tts_data_queue.empty():
            data1 = conn.tts_data_queue.get()
            if conn.status == WebsocketConnectionEvent.IDLE.value:
                frame_data = conn.opus_encoder.encode(data1, 320)
                await websocket.send_bytes(frame_data)
        else:
            await asyncio.sleep(0.01)


async def agent_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """LLM 环节，与 webrtc_aec3 模板一致（问题来源改为客户端识别文本）。"""
    # params 在 LLMFactories 里可为 NULL，链式 .get(params, None).get(...) 会炸 NoneType，
    # 这里用 `or {}` 兜底，逻辑与原模板一致
    _llm_params = conn.global_config.get("llm_config", {}).get("params") or {}
    if _llm_params.get("prologue", None):
        conn.llm_queue.put(_llm_params.get("prologue", None))
    chunk_nums = 0
    sentence_len = 10
    while conn.is_active:
        if not conn.llm_queue.empty():
            question = conn.llm_queue.get()
            all_reply = ""
            current_sentence = ""
            conn.dialogue_history.append({"role": "user", "content": question})
            start_time = time.perf_counter()
            async for _text in conn.llm_engine.response(conn.session_id, conn.dialogue_history, conn=conn):
                chunk_nums += 1
                if chunk_nums == 1:
                    cost_time = round((time.perf_counter() - start_time), 5)
                    LOG(f"{conn.llm_engine.name} 首token回复时间：{cost_time} 秒", "DEBUG")
                    await websocket.send_json({"type": WebsocketServerEvent.ANALYSIS.value, "text": f"response in {cost_time} seconds"})
                for text in _text:
                    if conn.status == WebsocketConnectionEvent.TALKING.value: break
                    current_sentence += text
                    all_reply += text
                    await websocket.send_json({"type": WebsocketServerEvent.ASSISTANT.value, "text": text})
                    await asyncio.sleep(0.005)
                    if current_sentence and len(current_sentence) > sentence_len and current_sentence[-1] in conn.punctuation_separator:
                        if current_sentence[-1] == ".":
                            if str(current_sentence[-2]) in "0123456789":
                                continue
                        sentence_len = 5
                        conn.tts_pending_queue.appendleft({"task_type": ServerInternalEvent.TTS.value, "text": current_sentence})
                        current_sentence = ""
                if conn.status == WebsocketConnectionEvent.TALKING.value:
                    await websocket.send_json({"type": "finish"})
                    conn.dialogue_history.append({"role": WebsocketServerEvent.ASSISTANT.value, "content": all_reply})
                    chunk_nums = 0
                    sentence_len = 10
                    LOG("LLM 回复被打断...", "DEBUG")
                    break
            # 处理剩余语句
            if current_sentence:
                conn.tts_pending_queue.appendleft({"task_type": ServerInternalEvent.TTS.value, "text": current_sentence})
            conn.dialogue_history.append({"role": "assistant", "content": all_reply})
            await websocket.send_json({"type": WebsocketServerEvent.FINISH.value})
            conn.tts_pending_queue.appendleft({"task_type": ServerInternalEvent.LLM_DONE.value})
            chunk_nums = 0
            sentence_len = 10
        else:
            await asyncio.sleep(0.01)


async def tts_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """TTS 环节，与 webrtc_aec3 模板一致。"""
    current_tts_task = None
    while conn.is_active:
        if conn.status == WebsocketConnectionEvent.TALKING.value:
            while len(conn.tts_pending_queue):
                text = conn.tts_pending_queue.pop()
                LOG(f"舍弃: {text}", "DEBUG")
            if current_tts_task:
                LOG(f"取消一个tts任务: {current_tts_task.get_name()}", "DEBUG")
                current_tts_task.cancel()
                current_tts_task = None
        elif len(conn.tts_pending_queue) or current_tts_task:
            if not current_tts_task:
                task = conn.tts_pending_queue.pop()
                if task["task_type"] == ServerInternalEvent.TTS.value:
                    tts_engine = conn.tts_engine
                    current_tts_task = asyncio.create_task(tts_engine.text_to_speak(task["text"], conn), name=task["text"])
                elif task["task_type"] == ServerInternalEvent.LLM_DONE.value:
                    await websocket.send_json({"type": WebsocketServerEvent.TTS_DONE.value})
                    LOG(f"向客户端推送tts音频结束消息", "DEBUG")
            elif current_tts_task.done():
                if current_tts_task.result():
                    current_tts_task = None
            else:
                ...
        await asyncio.sleep(0.008)


async def asr_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """服务端不做语音识别：本模板下为空实现。

    stream/views.py 会统一 gather 该协程，故必须保留函数签名；
    不去调用 asr_engine.initialize()，服务端 ASR 引擎在此模板中不建连。
    """
    while conn.is_active:
        await asyncio.sleep(0.1)
