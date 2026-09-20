from concurrent.futures import ThreadPoolExecutor
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
from queue import Queue
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
from pyaec3.api.PyAec3Lib import PyAec3
from FireRedVadCppLib import FireRedVadCpp
from collections import deque, OrderedDict
from fastapi import WebSocket, WebSocketDisconnect
from setting import *
from utils.getLogs import LOG
from utils.common.enumTaskType import WebsocketServerEvent, WebsocketClientEvent, ServerInternalEvent


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
        self.audio_chunk_queue = Queue()
        self.audio_buffer = deque()
        self.curren_tts_file_path = ""
        self.status = 0  # 0:silence 1:playing
        self.frame_size = 320
        self.global_config = {}
        self.is_active = True
        self.chat_mode = ""

        # asr
        self.all_cache = {}
        self.all_asr_data = []
        self.all_cur_start = False
        self.all_cur_end = False
        self.all_point = 0
        self.all_silence_duration = time.time()
        self.asr_pending_queue = Queue()
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

        # aec config
        self.pa = PyAec3()
        self.aec3_data_queue = Queue()

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
        # self.aec3_data_queue = Queue()
        # self.delay_time = time.time() * 1000
        
        # llm and tts and asr
        self.llm_queue = Queue()
        self.tts_data_queue = Queue()
        self.tts_text_queue = Queue()
        self.tts_pending_queue = deque()
        self.dialogue_history = []
        self.punctuation_separator = ['，', '。', '：', '！', '、', '。\n\n', '。\n', '?', '？', '。', "？", ",", ".", "、"]
        self.llm_engine = None
        self.tts_engine = None
        self.asr_engine = None
        self.in_recognize = False
        self.chunk_asr_client: WebSocket = None
        self.last_chunk_sentence = ""
        
        # 线程任务相关
        self.loop = asyncio.get_event_loop()
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=3)


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
                    conn.status = 1
                    await websocket.send_json({"type": WebsocketServerEvent.INTERRUPT.value})
            elif "bytes" in message:
                pcm_frame = conn.opus_decoder.decode(message["bytes"], 160)
                # print(f"{datetime.now()} 接收到一帧音频： {len(data1)} || 解码后的长度 {len(pcm_frame)}")
                conn.audio_chunk_queue.put((pcm_frame, 1))
    # except WebSocketDisconnect as e:
    #     LOG(f"server websocket close {e}")


async def send_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Send TTS/playback audio to client, storing each frame in far_end_buffer
    with a monotonic send_seq for later alignment."""
    while conn.is_active:
        if not conn.tts_data_queue.empty():
            data1 = conn.tts_data_queue.get()
            if conn.status == 0:
                # await websocket.send_bytes(data1)
                frame_data = conn.opus_encoder.encode(data1, 320)
                # print(f"{datetime.now()} before is {len(data1)} || after {len(frame_data)}")
                await websocket.send_bytes(frame_data)
        else:
            await asyncio.sleep(0.01)


async def recognize_asr_file(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while conn.is_active:
        if not conn.asr_pending_queue.empty():
            file_path = conn.asr_pending_queue.get()
            conn.in_recognize = True
            resp = await conn.asr_engine.speech_to_text(file_path, conn)
            LOG(f"语音识别结果: {resp}", "DEBUG")
            await websocket.send_json({"type": WebsocketServerEvent.TRANSCRIPTION.value, "text": resp["data"], "language": resp["language"]})
            if resp["data"]: conn.llm_queue.put(resp["data"])
            conn.in_recognize = False
        else:
            await asyncio.sleep(0.01)


async def webrtc_aec3(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Process mic audio with AEC+VAD using aligned far-end reference."""
    nums = 0
    while conn.is_active:
        if not conn.audio_chunk_queue.empty():
            item = conn.audio_chunk_queue.get()
            if conn.in_recognize:  continue
            # Unpack: (pcm_frame, last_played_seq)
            if isinstance(item, tuple):
                pcm_frame, last_played_seq = item
                # print(datetime.now(), f"last_played_seq is {last_played_seq}")
            else:
                # Legacy: raw bytes with no seq
                pcm_frame = item
                last_played_seq = -1
            if 1:
                _client_chunk = pcm_frame
                # # ---- Determine whether to use aligned AEC or legacy ----
                # try_aligned_aec = (
                #     conn.use_framed_protocol
                #     and last_played_seq > 0
                #     and len(conn.far_end_buffer) > 0
                # )

                # if try_aligned_aec:
                if 1:
                    # ---- Aligned AEC: look up far-end by last_played_seq ----
                    # far_end_audio = _get_aligned_far_end(conn, last_played_seq)

                    # if far_end_audio is not None:
                    if 1:
                        if (not conn.aec3_data_queue.empty()) and conn.chat_mode == "aec":
                            a = conn.aec3_data_queue.get()
                            chunk1 = np.frombuffer(a, dtype=np.int16)
                            chunk2 = np.frombuffer(_client_chunk, dtype=np.int16)
                            aec3_res = conn.pa.aecProcess(chunk1, chunk2, 160, 16000, 320)
                        else:
                            aec3_res = _client_chunk
                            
                        # client_chunk = _client_chunk
                        
                        # aec3_res = _client_chunk

                        # aec3_res = conn.pa.aecProcess(chunk1, chunk2, 160, 16000, 320)
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
                                if conn.global_config.get("asr_config").get("params").get("stream_asr_mode") == "chunk":
                                    await conn.chunk_asr_client.send(json.dumps({"type": WebsocketServerEvent.STOP_LISTENING.value}, ensure_ascii="utf-8"))
                                conn.status = 0
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
                                conn.asr_pending_queue.put(file_path)
                                conn.client_voice_window.clear()

                        if client_have_voice:
                            conn.collect_previous = False
                            conn.client_have_voice = True
                            conn.last_activity_time = time.time() * 1000
                            conn.all_point += 1

                        if conn.client_have_voice:
                            conn.all_asr_data.append(aec3_res)
                            if conn.global_config.get("asr_config").get("params").get("stream_asr_mode") != "chunk":
                                if len(conn.all_asr_data) % 30 == 0:
                                    # 进行实时语音识别
                                    audio_in = b"".join(conn.previous_frame_list + conn.all_asr_data)
                                    await conn.chunk_asr_client.send(audio_in)
                            else:
                                # chunk recog
                                await conn.chunk_asr_client.send(aec3_res)

                        if conn.all_point == 1:
                            conn.collect_previous = False
                            conn.client_have_voice = True
                            conn.last_activity_time = time.time() * 1000
                            conn.all_point += 1
                            LOG("开始监听333...", "DEBUG")
                            conn.status = 1
                            await websocket.send_json({"type": WebsocketServerEvent.INTERRUPT.value})
                            await websocket.send_json({"type": WebsocketServerEvent.START_LISTENING.value})
                            conn.previous_frame_list = conn.previous_frame.get_all_items()
                            if conn.global_config.get("asr_config").get("params").get("stream_asr_mode") == "chunk":
                                await conn.chunk_asr_client.send(json.dumps({"type": WebsocketServerEvent.START_LISTENING.value}, ensure_ascii="utf-8"))
                                await conn.chunk_asr_client.send(b''.join(conn.previous_frame_list))
        else:
            await asyncio.sleep(0.001)


async def get_llm_result(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    if conn.global_config.get("llm_config", {}).get("params", None).get("prologue", None):
        conn.llm_queue.put(conn.global_config.get("llm_config", {}).get("params", None).get("prologue", None))
        # await asyncio.sleep(2)
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
                    if conn.status == 1: break
                    current_sentence += text
                    all_reply += text
                    await websocket.send_json({"type": WebsocketServerEvent.ASSISTANT.value, "text": text})
                    await asyncio.sleep(0.005)
                    if current_sentence and len(current_sentence) > sentence_len and current_sentence[-1] in conn.punctuation_separator:
                        if current_sentence[-1] == ".":
                            if str(current_sentence[-2]) in "0123456789":
                                continue
                        sentence_len = 5
                        # LOG(f"{datetime.now()} 开始合成 LLM 回复 {current_sentence}", "DEBUG")
                        conn.tts_pending_queue.appendleft({"task_type": ServerInternalEvent.TTS.value, "text": current_sentence})
                        current_sentence = ""
                if conn.status == 1:
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


async def get_tts_path_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    current_tts_task = None
    while conn.is_active:
        if conn.status == 1:
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
                    # print(f"创建任务：{text}")
                    # tts_engine = deepcopy(conn.tts_engine)  # 待优化
                    tts_engine = conn.tts_engine
                    current_tts_task = asyncio.create_task(tts_engine.text_to_speak(task["text"], conn), name=task["text"])
                elif task["task_type"] == ServerInternalEvent.LLM_DONE.value:
                    await websocket.send_json({"type": WebsocketServerEvent.TTS_DONE.value})
                    LOG(f"向客户端推送tts音频结束消息", "DEBUG")
            elif current_tts_task.done():
                if current_tts_task.result():
                    # conn.tts_data_queue.put(current_tts_task.result())
                    current_tts_task = None
            else:
                ...
                # conn.tts_pending_queue.append(text)
        await asyncio.sleep(0.008)


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


async def stream_asr_realtime_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    await conn.asr_engine.initialize(websocket, conn)