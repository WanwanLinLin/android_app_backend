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
from collections import OrderedDict, deque
from pydub import AudioSegment
from pyaec3.api.PyAec3Lib import PyAec3
from FireRedVadCppLib import FireRedVadCpp
from collections import deque, OrderedDict
from fastapi import WebSocket, WebSocketDisconnect
from pydub import AudioSegment
from datetime import datetime
from setting import *
from utils.getLogs import LOG


class AsyncWavReader:
    def __init__(self, path, frame_size):
        self.path = path
        self.frame_size = frame_size
        self.frame_bytes = frame_size * 2  # 16bit 单声道
        self.fh = None
        self.data_offset = 0

    async def open(self):
        # 异步打开文件 + 解析wav头
        self.fh = await aiofiles.open(self.path, "rb")
        # 跳过RIFF头(44字节标准wav)
        header = await self.fh.read(44)
        # 定位到音频数据起始位置
        self.data_offset = 44
        await self.fh.seek(self.data_offset)

    async def read_frame(self):
        # 异步读取一帧音频
        data = await self.fh.read(self.frame_bytes)
        return data

    async def close(self):
        if self.fh:
            await self.fh.close()


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

        # asr
        self.all_cache = {}
        self.all_asr_data = []
        self.all_cur_start = False
        self.all_cur_end = False
        self.all_point = 0
        self.all_silence_duration = time.time()
        self.asr_pending_queue = Queue()

        # sliding window for voice detection
        self.client_voice_window = deque(maxlen=60)
        self.frame_window_threshold = 60

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

        # aec config
        self.pa = PyAec3()

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
        self.llm_queue = Queue()
        self.tts_path_queue = Queue()
        self.tts_text_queue = Queue()
        self.tts_pending_queue = deque()
        self.dialogue_history = []
        self.punctuation_separator = ['，', '。', '：', '！', '、', '。\n\n', '。\n', '?', '？', '。', "？"]
        self.llm_engine = None
        self.tts_engine = None
        self.asr_engine = None


# ============================================================
# Binary framing constants (must match client)
# ============================================================
async def receive_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Receive audio from client. Auto-detects framed (MICK) vs raw PCM."""
    nums = 0
    while True:
        data = await websocket.receive_bytes()

        # ---- Auto-detect framed protocol on first packet ----
        if not conn.use_framed_protocol and data[:4] == FRAME_MAGIC:
            conn.use_framed_protocol = True
            LOG("[INFO] Detected framed (MICK) protocol from client", "DEBUG")

        if conn.use_framed_protocol:
            # ---- Framed protocol: parse header, extract metadata ----
            conn.framed_partial += data

            # while len(conn.framed_partial) >= FRAME_HEADER_SIZE:
            if 1:
                # Parse header
                magic, timestamp_ms, last_played_seq, seq, audio_len = struct.unpack_from(
                    ">4sIIIH", conn.framed_partial, 0
                )
                if magic != FRAME_MAGIC:
                    # Corrupted — skip one byte and retry
                    conn.framed_partial = conn.framed_partial[1:]
                    continue

                total_len = FRAME_HEADER_SIZE + audio_len
                if len(conn.framed_partial) < total_len:
                    break  # wait for more data

                # Extract audio and metadata
                audio_data = conn.framed_partial[FRAME_HEADER_SIZE:total_len]
                conn.framed_partial = conn.framed_partial[total_len:]
                # nums += 1
                # if nums % 50 == 0:
                #     print("last_played_seq is ", last_played_seq)
                conn.audio_chunk_queue.put((audio_data, last_played_seq))


async def send_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Send TTS/playback audio to client, storing each frame in far_end_buffer
    with a monotonic send_seq for later alignment."""
    while True:
        if not conn.tts_path_queue.empty():
            file_path = conn.tts_path_queue.get()
            reader = AsyncWavReader(
                path=file_path,
                frame_size=160,
            )
            await reader.open()
            while True:
                if conn.status == 1: break  # 打断tts数据传输
                data1 = await reader.read_frame()
                if len(data1) < 160 * 2:
                    # Last partial frame
                    await websocket.send_bytes(data1)
                    conn.send_seq += 1
                    conn.far_end_buffer[conn.send_seq] = data1
                    conn.far_end_seq_list.append(conn.send_seq)
                    break

                await websocket.send_bytes(data1)
                conn.send_seq += 1
                conn.far_end_buffer[conn.send_seq] = data1
                conn.far_end_seq_list.append(conn.send_seq)

            await reader.close()
            LOG(f"向服务端发送 {conn.send_seq} 个音频", "DEBUG")
        else:
            await asyncio.sleep(0.01)


async def recognize_asr_file(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while 1:
        if not conn.asr_pending_queue.empty():
            file_path = conn.asr_pending_queue.get()
            resp = await conn.asr_engine.speech_to_text(file_path, conn)
            LOG(f"语音识别结果: {resp}", "DEBUG")
            await websocket.send_json({"type": "transcription", "text": resp["data"], "language": resp["language"]})
            conn.llm_queue.put(resp["data"])
        else:
            await asyncio.sleep(0.01)


def _get_aligned_far_end(conn: ConnectionObjectCustomAec3, last_played_seq):
    """Look up the far-end reference frame for the given playback sequence.

    Uses last_played_seq minus AEC_DELAY_OFFSET to account for acoustic
    delay between speaker output and microphone pickup.
    """
    # Acoustic delay offset: ~2 frames (20ms) at 16kHz/10ms frames.
    # Tune this based on your hardware setup.
    # print("lastPlayedSeq is : ", last_played_seq)
    target_seq = max(1, last_played_seq - AEC_DELAY_OFFSET)
    return conn.far_end_buffer.get(target_seq, None)


async def webrtc_aec3(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    """Process mic audio with AEC+VAD using aligned far-end reference."""

    while True:
        if not conn.audio_chunk_queue.empty():
            item = conn.audio_chunk_queue.get()
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
                # ---- Determine whether to use aligned AEC or legacy ----
                try_aligned_aec = (
                    conn.use_framed_protocol
                    and last_played_seq > 0
                    and len(conn.far_end_buffer) > 0
                )

                if try_aligned_aec:
                    # ---- Aligned AEC: look up far-end by last_played_seq ----
                    far_end_audio = _get_aligned_far_end(conn, last_played_seq)

                    if far_end_audio is not None:
                        client_chunk = _client_chunk
                        chunk1 = np.frombuffer(far_end_audio, dtype=np.int16)
                        chunk2 = np.frombuffer(client_chunk, dtype=np.int16)

                        aec3_res = conn.pa.aecProcess(chunk1, chunk2, 160, 16000, 320)
                        # aec3_res = _client_chunk
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
                                conn.status = 0
                                file_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
                                pcm_data = conn.previous_frame.get_all_items() + conn.all_asr_data
                                with wave.open(file_path, "wb") as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(16000)
                                    wf.writeframes(b"".join(pcm_data))
                                conn.client_voice_stop = True
                                conn.collect_previous = True
                                conn.client_have_voice = False
                                conn.all_asr_data = []
                                conn.all_point = 0
                                conn.asr_pending_queue.put(file_path)

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
                            await websocket.send_json({"type": "interrupt"})
                            conn.status = 1

                        # frame_list.append(aec3_res)
                        # origin_list.append(client_chunk)
                    else:
                        ...
                        # far_end not found — fall through to direct VAD
                        _direct_vad(conn, _client_chunk)
                else:
                    # ---- Direct VAD (no far-end available) ----
                    _direct_vad(conn, _client_chunk, websocket)
        else:
            await asyncio.sleep(0.001)


def _direct_vad(conn: ConnectionObjectCustomAec3, client_chunk, websocket=None):
    """Direct VAD processing (no AEC). Shared by both aligned and legacy paths."""
    vad_chunk = np.frombuffer(client_chunk, dtype=np.int16)
    vad_res = conn.frv.process_stream(vad_chunk, 160)

    if conn.collect_previous:
        conn.previous_frame.enqueue(client_chunk)
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
            conn.status = 0
            file_path = config_data["CACHE"]["tts"] + str(uuid.uuid4()) + ".wav"
            pcm_data = conn.previous_frame.get_all_items() + conn.all_asr_data
            with wave.open(file_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"".join(pcm_data))
            conn.client_voice_stop = True
            conn.collect_previous = True
            conn.client_have_voice = False
            conn.all_asr_data = []
            conn.all_point = 0
            conn.asr_pending_queue.put(file_path)

    if client_have_voice:
        conn.collect_previous = False
        conn.client_have_voice = True
        conn.last_activity_time = time.time() * 1000
        conn.all_point += 1

    if conn.client_have_voice:
        conn.all_asr_data.append(client_chunk)

    if conn.all_point == 1:
        conn.collect_previous = False
        conn.client_have_voice = True
        conn.last_activity_time = time.time() * 1000
        conn.all_point += 1
        LOG("开始监听222...", "DEBUG")
        conn.status = 1


async def get_llm_result(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while 1:
        if not conn.llm_queue.empty():
            question = conn.llm_queue.get()
            all_reply = ""
            current_sentence = ""
            conn.dialogue_history.append({"role": "user", "content": question})
            async for text in conn.llm_engine.response(conn.session_id, conn.dialogue_history):
                current_sentence += text
                all_reply += text
                await websocket.send_json({"type": "assistant", "text": text})
                if conn.status != 0:
                    await websocket.send_json({"type": "finish"})
                    conn.dialogue_history.append({"role": "assistant", "content": all_reply})
                    LOG("LLM 回复被打断...", "DEBUG")
                    break
                # conn.tts_text_queue.put(text)
                if current_sentence and len(current_sentence) > 10 and current_sentence[-1] in conn.punctuation_separator:
                    tts_task = asyncio.create_task(conn.tts_engine.text_to_speak(current_sentence, conn))
                    conn.tts_pending_queue.appendleft(tts_task)
                    current_sentence = ""
            conn.dialogue_history.append({"role": "assistant", "content": all_reply})
            await websocket.send_json({"type": "finish"})
        else:
            await asyncio.sleep(0.01)


async def get_tts_path_monitor(websocket: WebSocket, conn: ConnectionObjectCustomAec3):
    while 1:
        if conn.status == 1:
            while len(conn.tts_pending_queue):
                t = conn.tts_pending_queue.pop()
                t.cancel()
                LOG(f"{datetime.now()} 取消一个tts任务！", "DEBUG")
        elif len(conn.tts_pending_queue):
            current_tts_task = conn.tts_pending_queue.pop()
            if not current_tts_task.done():
                conn.tts_pending_queue.append(current_tts_task)
            else:
                if current_tts_task.result():
                    conn.tts_path_queue.put(current_tts_task.result())
        await asyncio.sleep(0.008)
