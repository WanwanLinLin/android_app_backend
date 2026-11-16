from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
import wave
import uuid
import json
import struct
import base64
import random
import uvicorn
import aiohttp
import asyncio
import websockets
import numpy as np
import time
import uuid
import random
import aiohttp
import aiofiles
import struct
import opuslib_next
from copy import deepcopy
from collections import OrderedDict, deque
from pydub import AudioSegment
from fireredvad import FireRedVadCpp
from collections import deque, OrderedDict
from fastapi import WebSocket, WebSocketDisconnect
from setting import *
from utils.getLogs import LOG
from utils.common.enumTaskType import WebsocketServerEvent, WebsocketClientEvent, ServerInternalEvent, WebsocketConnectionEvent


class LimitedQueue:
    def __init__(self, max_length):
        self.queue = deque()
        self.max_length = max_length

    def enqueue(self, item):
        if len(self.queue) >= self.max_length:
            self.queue.popleft()  # 移除前端元素
            self.queue.append(item)
        else:
            self.queue.append(item)

    def dequeue(self):
        if self.queue:
            return self.queue.popleft()
        else:
            raise IndexError("dequeue from an empty queue")

    def get_all_items(self):
        res = []
        for i in range(len(self.queue)):
            res.append(self.queue.popleft())
        return res

    def __len__(self):
        return len(self.queue)

    def __repr__(self):
        return f"LimitedQueue({list(self.queue)})"


class ConnectionObjectCustomAec3:
    def __init__(self, uid: str, vad_max_thre=0.9, vad_min_thre=0.65,
                 silence_threshold_ms=800):
        self.uid = uid
        self.session_id = str(uuid.uuid4())
        self.frames_asr_online = []
        self.tts_chunk_queue = deque()
        self.buffer_size = 0
        # 会话内各协程间的队列一律 asyncio.Queue（2026-11-10）：消费者
        # await get() 挂起等待，替代此前 sleep(0.001~0.01) 忙等轮询；
        # 生产者全部是同事件循环协程（含 providers 插件），put_nowait 安全
        self.audio_chunk_queue = asyncio.Queue()
        self.audio_buffer = deque()
        self.curren_tts_file_path = ""
        self.status = WebsocketConnectionEvent.IDLE.value  # 0:idle 1:talking
        self.frame_size = 320
        self.global_config = {}
        self.is_active = True

        # asr
        self.all_cache = {}
        self.all_asr_data = []
        self.all_cur_start = False
        self.all_cur_end = False
        self.all_point = 0
        self.all_silence_duration = time.time()
        self.asr_pending_queue = asyncio.Queue()
        self.current_language = ""   # 当前语言，用于多语种语音合成

        # sliding window for voice detection
        self.client_voice_window = deque(maxlen=60)
        self.frame_window_threshold = 30

        # vad config
        self.frv = FireRedVadCpp()
        self.previous_frame = LimitedQueue(max_length=100)
        self.collect_previous = True
        self.silence_threshold_ms = silence_threshold_ms
        self.client_audio_buffer = bytearray()
        self.vad_max_thre = vad_max_thre
        self.vad_min_thre = vad_min_thre
        self.last_is_voice = False
        self.client_have_voice = False
        self.last_activity_time = 0.0
        self.client_voice_stop = False
        self.previous_frame_list = []
        self.opus_decoder = opuslib_next.Decoder(16000, 1)
        self.opus_encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)

        # ---- NEW: far-end reference buffer for aligned AEC ----
        # Maps send_seq -> raw audio bytes (the far-end reference)
        self.far_end_buffer = OrderedDict()
        self.far_end_seq_list = deque()  # ordered send_seq for cleanup
        self.send_seq = 0  # monotonic counter for each sent audio frame
        self.far_end_max_size = 0  # keep last N frames (~20s at 10ms/frame)
        self.current_max_seq = 0
        # ---- NEW: framed protocol state ----
        self.use_framed_protocol = False  # auto-detected on first packet
        self.framed_partial = b""  # leftover bytes for framed parsing

        # llm and tts and asr
        self.llm_queue = asyncio.Queue()
        self.tts_data_queue = asyncio.Queue()
        # tts_text_queue 全库无读写方（僵尸字段），2026-11-10 移除
        self.tts_pending_queue = deque()
        # TTS 待合成队列的新任务通知：tts_process_monitor 空闲时挂起等
        # 待本事件，替代忙等轮询（生产者 appendleft 后 set）
        self.tts_pending_event = asyncio.Event()
        self.dialogue_history = []
        self.punctuation_separator = ['，', '。', '：', '！', '、', '。\n\n', '。\n', '?', '？', '。', "？", ",", ".", "、"]
        self.llm_engine = None
        self.tts_engine = None
        self.asr_engine = None
        self.in_recognize = False
        self.chunk_asr_client: WebSocket = None
        self.last_chunk_sentence = ""
        # stream/views.py 建连后挂入：供 providers 插件（LLM/TTS/ASR）在报错时
        # 直接通过 send_error_to_client 向终端推送错误事件
        self.websocket: WebSocket = None
        
        # 线程任务相关
        self.loop = asyncio.get_event_loop()
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=2)

    def push_tts_task(self, task: dict):
        """tts_pending_queue 唯一生产者入口：入队并唤醒事件驱动的 tts_process_monitor。"""
        self.tts_pending_queue.appendleft(task)
        self.tts_pending_event.set()

    # 对话历史上限：数字人终端可能全天在线，dialogue_history 此前无上限，
    # 上下文无限增长 → 内存与每轮 LLM token 成本线性上涨。保留最近 60 条
    # （约 30 轮），从最旧端淘汰（每轮定长追加 user+assistant 成对，偶数
    # 上限保证淘汰后仍是完整轮次）。
    DIALOGUE_HISTORY_MAX = 60

    def append_dialogue(self, role: str, content: str):
        """dialogue_history 唯一追加入口：追加并按 DIALOGUE_HISTORY_MAX 截尾。"""
        self.dialogue_history.append({"role": role, "content": content})
        overflow = len(self.dialogue_history) - self.DIALOGUE_HISTORY_MAX
        if overflow > 0:
            del self.dialogue_history[:overflow]


# ============================================================
# Binary framing constants (must match client)
# ============================================================
async def receive_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Receive audio from client. Auto-detects framed (MICK) vs raw PCM."""
    # try:
    while conn.is_active:
        # data1 = await websocket.receive_bytes()
        # pcm_frame = conn.opus_decoder.decode(data1, 160)
        # # print(f"{datetime.now()} 接收到一帧音频： {len(data1)} || 解码后的长度 {len(pcm_frame)}")
        # conn.audio_chunk_queue.put((pcm_frame, 1))
        
        message = await websocket.receive()
        if message["type"] == "websocket.receive":
            if "text" in message:
                command = json.loads(message["text"])
                LOG(f"收到客户端指令消息：{command}", "DEBUG")
                if command["type"] == WebsocketClientEvent.WAKEUP.value:
                    conn.status = WebsocketConnectionEvent.TALKING.value
                    await websocket.send_json({"type": WebsocketServerEvent.INTERRUPT.value})
            elif "bytes" in message:
                pcm_frame = conn.opus_decoder.decode(message["bytes"], 160)
                # print(f"{datetime.now()} 接收到一帧音频： {len(data1)} || 解码后的长度 {len(pcm_frame)}")
                conn.audio_chunk_queue.put_nowait((pcm_frame, 1))
    # except WebSocketDisconnect as e:
    #     LOG(f"server websocket close {e}")


async def send_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Send TTS/playback audio to client."""
    # 空闲时挂在 queue.get() 上，有帧即被唤醒；is_active=False 时靠
    # wait_for 超时回检退出（2026-11-10：替代 sleep(0.01) 忙等）
    while conn.is_active:
        try:
            data1 = await asyncio.wait_for(conn.tts_data_queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        if conn.status == WebsocketConnectionEvent.IDLE.value:
            frame_data = conn.opus_encoder.encode(data1, 320)
            await websocket.send_bytes(frame_data)


async def recognize_asr_file(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while conn.is_active:
        try:
            file_path = await asyncio.wait_for(conn.asr_pending_queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        conn.in_recognize = True
        try:
            resp = await conn.asr_engine.speech_to_text(file_path, conn)
            # realtime 类插件的 speech_to_text 是空实现（返回 None，识别结果
            # 由它们自己的链路推送）；此处按无结果跳过，不能再取 resp 键。
            if resp:
                LOG(f"语音识别结果: {resp}", "DEBUG")
                await websocket.send_json({"type": WebsocketServerEvent.TRANSCRIPTION.value, "text": resp["data"], "language": resp["language"]})
                if resp["data"]: conn.llm_queue.put_nowait(resp["data"])
        except Exception as e:
            LOG(f"整句语音识别失败: {e}", "ERROR")
        finally:
            # 临时 WAV 统一在此清理：此前仅个别非实时插件内部自删，
            # 识别异常或插件不自删时文件永久残留，CACHE 目录只增不减
            try:
                os.remove(file_path)
            except OSError:
                pass
            conn.in_recognize = False


async def webrtc_aec3(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Process mic audio with local VAD (server-side AEC removed, client does AEC)."""
    # 忙等改造（2026-11-10）：await 队列取帧替代 sleep(0.001) 轮询。
    # 识别进行中（in_recognize）的帧仍按原语义丢弃——句尾音频此时已定格
    # 成 wav 送去识别，残留帧若回灌反而会让滑动窗口 client_voice_window
    # 出现音频突刺、破坏判起判尾时序，故维持丢弃。
    while conn.is_active:
        try:
            item = await asyncio.wait_for(conn.audio_chunk_queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        if conn.in_recognize:
            continue
        # Unpack: (pcm_frame, last_played_seq)
        if isinstance(item, tuple):
            pcm_frame, last_played_seq = item
        else:
            # Legacy: raw bytes with no seq
            pcm_frame = item
            last_played_seq = -1
        # 服务端 AEC（pyaec3）已移除：回声消除由客户端完成，麦克风原始帧直接进 VAD
        aec3_res = pcm_frame
        chunk3 = np.frombuffer(aec3_res, dtype=np.int16)
        vad_res = conn.frv.process_stream(chunk3, 160)

        if conn.collect_previous:
            conn.previous_frame.enqueue(aec3_res)
        if vad_res.confidence > conn.vad_max_thre:
            is_voice = True
        elif vad_res.confidence < conn.vad_min_thre:
            is_voice = False
        else:
            is_voice = conn.last_is_voice

        conn.last_is_voice = is_voice
        conn.client_voice_window.append(is_voice)
        client_have_voice = (
            conn.client_voice_window.count(True) >= conn.frame_window_threshold
        )

        if conn.client_have_voice and not client_have_voice:
            stop_duration = time.time() * 1000 - conn.last_activity_time
            if stop_duration >= conn.silence_threshold_ms:
                LOG("停止监听！", "DEBUG")
                await websocket.send_json({"type": WebsocketServerEvent.STOP_LISTENING.value})
                conn.status = WebsocketConnectionEvent.IDLE.value
                file_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
                pcm_data = conn.previous_frame_list + conn.all_asr_data
                with wave.open(file_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"".join(pcm_data))
                conn.client_voice_stop = True
                conn.collect_previous = True
                conn.client_have_voice = False
                conn.all_asr_data = []
                conn.previous_frame_list = []
                conn.last_chunk_sentence = ""
                conn.all_point = 0
                conn.asr_pending_queue.put_nowait(file_path)
                conn.client_voice_window.clear()

        if client_have_voice:
            conn.collect_previous = False
            conn.client_have_voice = True
            conn.last_activity_time = time.time() * 1000
            conn.all_point += 1

        if conn.client_have_voice:
            conn.all_asr_data.append(aec3_res)

        if conn.all_point == 1:
            conn.collect_previous = False
            conn.client_have_voice = True
            conn.last_activity_time = time.time() * 1000
            conn.all_point += 1
            LOG("开始监听333...", "DEBUG")
            conn.status = WebsocketConnectionEvent.TALKING.value
            await websocket.send_json({"type": WebsocketServerEvent.INTERRUPT.value})
            await websocket.send_json({"type": WebsocketServerEvent.START_LISTENING.value})
            conn.previous_frame_list = conn.previous_frame.get_all_items()


async def agent_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    # params 可为 NULL（LLMFactories 列可为空、个性插件模板必含键但值可空），
    # 链式 .get("params", None).get(...) 会在 None 上取键直接 AttributeError，
    # 且本协程在 asyncio.gather 里抛出会连带终止整条会话。与 agent2tts_noasr
    # 模板同款修复：`or {}` 兜底。
    _llm_params = conn.global_config.get("llm_config", {}).get("params") or {}
    if _llm_params.get("prologue", None):
        conn.llm_queue.put_nowait(_llm_params.get("prologue", None))
        # await asyncio.sleep(2)
    chunk_nums = 0
    sentence_len = 15
    while conn.is_active:
        try:
            question = await asyncio.wait_for(conn.llm_queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        all_reply = ""
        current_sentence = ""
        interrupted = False
        conn.append_dialogue("user", question)
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
                await asyncio.sleep(0.001)
                if current_sentence and len(current_sentence) > sentence_len and current_sentence[-1] in conn.punctuation_separator:
                    if current_sentence[-1] == ".":
                        if str(current_sentence[-2]) in "0123456789":
                            continue
                    sentence_len = 10
                    # LOG(f"{datetime.now()} 开始合成 LLM 回复 {current_sentence}", "DEBUG")
                    conn.push_tts_task({"task_type": ServerInternalEvent.TTS.value, "text": current_sentence})
                    current_sentence = ""
            if conn.status == WebsocketConnectionEvent.TALKING.value:
                await websocket.send_json({"type": "finish"})
                conn.append_dialogue(WebsocketServerEvent.ASSISTANT.value, all_reply)
                # 打断：此处已落库本轮部分回复。此前的 break 只跳出 async for，
                # 控制权回到下面的"处理剩余语句"，尾部再 append 一次 assistant，
                # 历史变成 user+assistant+assistant 重复轮次，污染后续上下文
                # （2026-11-11 修复：置 interrupted，尾部不再重复追加）。
                interrupted = True
                chunk_nums = 0
                sentence_len = 15
                LOG("LLM 回复被打断...", "DEBUG")
                break
        # 处理剩余语句
        if current_sentence:
            conn.push_tts_task({"task_type": ServerInternalEvent.TTS.value, "text": current_sentence})
        if not interrupted:
            conn.append_dialogue("assistant", all_reply)
        await websocket.send_json({"type": WebsocketServerEvent.FINISH.value})
        conn.push_tts_task({"task_type": ServerInternalEvent.LLM_DONE.value})
        chunk_nums = 0
        sentence_len = 15


async def tts_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    current_tts_task = None
    while conn.is_active:
        # 循环顶部清事件：与下面的 deque 检查之间无 await 点（单线程事件循环
        # 下原子），不会出现「生产者 set 后又被 clear」的丢失唤醒；若有新任务
        # 被漏处理，也只是多一次空转回检，不会卡死。
        conn.tts_pending_event.clear()
        if conn.status == WebsocketConnectionEvent.TALKING.value:
            while len(conn.tts_pending_queue):
                text = conn.tts_pending_queue.pop()
                LOG(f"舍弃: {text}", "DEBUG")
            if current_tts_task:
                LOG(f"取消一个tts任务: {current_tts_task.get_name()}", "DEBUG")
                current_tts_task.cancel()
                current_tts_task = None
            # 打断态必须有 await（本分支丢弃后可能无任何在途任务，直接
            # 回循环顶会同步死循环饿死事件循环）：挂起等新任务（到来即
            # 唤醒丢弃）或 0.05s 回检状态恢复。
            try:
                await asyncio.wait_for(conn.tts_pending_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass
        elif len(conn.tts_pending_queue) or current_tts_task:
            if not current_tts_task:
                task = conn.tts_pending_queue.pop()
                if task["task_type"] == ServerInternalEvent.TTS.value:
                    # print(f"创建任务：{text}")
                    # tts_engine = deepcopy(conn.tts_engine)  # 待优化
                    tts_engine = conn.tts_engine
                    current_tts_task = asyncio.create_task(tts_engine.text_to_speak(task["text"], conn), name=task["text"])
                elif task["task_type"] == ServerInternalEvent.LLM_DONE.value:
                    await websocket.send_json({"type": WebsocketServerEvent.TTS_DONE.value})
                    LOG(f"向客户端推送tts音频结束消息", "DEBUG")
            elif current_tts_task.done():
                # result() 会把任务内部异常重新抛出（TTS 网络抖动/超时很常见）：
                # 不捕获则异常沿本协程进入 gather、整条会话断开。单句合成失败
                # 只丢弃该句并记日志，会话继续。
                try:
                    current_tts_task.result()
                except asyncio.CancelledError:
                    LOG("TTS 任务已取消（打断）", "DEBUG")
                except Exception as e:
                    LOG(f"TTS 任务异常，丢弃该句: {e}", "ERROR")
                current_tts_task = None
            else:
                # 有任务在途：等其完成即刻返回；0.01s 上限用于及时感知
                # status 翻转为 TALKING（打断）。在途期间新入队任务本就串行
                # 等待，无需事件唤醒。
                await asyncio.wait({current_tts_task}, timeout=0.01)
                continue
        else:
            # 完全空闲（无待合成、无在途任务、非播报中）：挂起等事件，最长
            # 0.1s 回检 status，空闲连接近乎零 CPU（替代原恒定 sleep(0.008)）。
            try:
                await asyncio.wait_for(conn.tts_pending_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
            continue


async def send_asr_chunk(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while conn.is_active:
        _text = await conn.chunk_asr_client.recv()
        text = json.loads(_text, strict=False)
        if not conn.last_chunk_sentence:
            conn.last_chunk_sentence = text["text"]
            await websocket.send_json(text)
            await asyncio.sleep(0.001)
        else:
            if text["text"] != conn.last_chunk_sentence:
                await websocket.send_json(text)
                conn.last_chunk_sentence = text["text"]
                await asyncio.sleep(0.001)


async def asr_process_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """ASR 编排入口（stream/views.py 统一 gather）。按引擎能力分流：

    - 实时引擎（qwen3_asr_realtime / qwen3_asr_flash_realtime）自带 initialize：
      音频流转发、VAD 事件、整句识别结果均由引擎内部链路完成。
    - 非实时引擎（qwen3_asr / generic_asr）只有 speech_to_text，没有 initialize。
      此前无条件调 initialize，选中即 AttributeError 炸掉整条会话；且
      recognize_asr_file 从未被 gather，本地判尾 → 整句识别链路实际不可用。
      （2026-11-10 修复）此分支走本地 FireRedVAD 判尾写临时 wav → 识别；
      两个协程都只在本地链路里消费 audio_chunk_queue，不与实时引擎抢帧。
    """
    if hasattr(conn.asr_engine, "initialize"):
        await conn.asr_engine.initialize(websocket, conn)
    else:
        await asyncio.gather(
            webrtc_aec3(websocket, conn),
            recognize_asr_file(websocket, conn),
        )


async def start_session():
    # 1.创建聊天记录
    ...


async def finish_session():
    # 1.保存对话上下文
    ...