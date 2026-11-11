import torch

import re
import os
import time
import wave
import uuid
import yaml
import logging
import asyncio
import uvicorn
import aiohttp
import numpy as np
from queue import Queue
from collections import deque
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from fireredvad import FireRedVadCpp
from funasr import AutoModel
from datetime import datetime

yaml_path = "../../config.yaml"
with open(yaml_path, 'r') as file:
    config_data = yaml.load(file, Loader=yaml.FullLoader)


VAD_MODEL_FILES = (
    "firered_vad_packed_cache_stream.ncnn.param",
    "firered_vad_packed_cache_stream.ncnn.bin",
    "cmvn_means_stream.bin",
    "cmvn_istd_stream.bin",
)


def vad_model_paths(base_path: str = "") -> tuple:
    """优先用 config.yaml MODEL_CONFIG 指定的外部模型目录，缺失时回退到 fireredvad 包内置模型。"""
    import fireredvad

    if base_path and os.path.exists(os.path.join(base_path, VAD_MODEL_FILES[0])):
        return tuple(os.path.join(base_path, name) for name in VAD_MODEL_FILES)
    return tuple(fireredvad.model_path(name) for name in VAD_MODEL_FILES)


app = FastAPI()
CHUNK_SIZE = 320
# CHUNK_SIZE = 1920
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
def print_log(text): print(f"{datetime.now()} {text}")

model_asr = AutoModel(
    model="../../models/SenseVoiceSmall",
    ncpu=1,
    device="cuda:0",
    disable_pbar=True,
    disable_log=True,
    disable_update=True
)
test_asr_result = model_asr.generate(input="./example.wav")
print_log(f"test_asr_result: {test_asr_result}")


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


class ConnectionObjectCustomVadV2:
    def __init__(self, uid: str, vad_model_path: str = None, vad_max_thre = 0.9, vad_min_thre = 0.65,
                 silence_threshold_ms = 800, use_aed = False):
        self.uid = uid
        self.frames_asr_online = []
        self.msg_queue = Queue()
        self.audio_buffer = deque()
        self.buffer_size = 0
        self.audio_chunk_queue = Queue()
        self.cur_users = False
        self.all_cache = {}
        self.all_asr_data = []
        self.all_cur_start = False
        self.all_cur_end = False
        self.all_point = 0
        self.all_silence_duration = time.time()  # 初始化静默时长
        # self.previous_frame = LimitedQueue(max_length=60)
        self.previous_frame = LimitedQueue(max_length=100)
        self.collect_previous = True
        self.frame_count = 0
        self.linear_contiguous_queue = []
        
        self.client_have_voice = False
        self.last_activity_time = 0.0  # 统一的活动时间戳（毫秒）
        self.client_voice_stop = False
        # self.client_voice_window = deque(maxlen=60)
        self.client_voice_window = deque(maxlen=60)
        self.last_is_voice = False
        # self.frame_window_threshold = 30
        self.frame_window_threshold = 10
        self.silence_threshold_ms = silence_threshold_ms
        self.client_audio_buffer = bytearray()
        self.vad_max_thre = vad_max_thre
        self.vad_min_thre = vad_min_thre
        self.use_aed = use_aed
        
        # firered-vad cpp 高性能版（模型随 fireredvad 包发布，外部路径缺失时自动回退）
        self.firered_vad = FireRedVadCpp()
        self.firered_vad.init(
            *vad_model_paths(config_data["MODEL_CONFIG"][0]["path"]),
            16000, 10, 25, 0.9,
        )
        
        # 流式 ASR
        self.stt_msg_queue = Queue()
        self.previous_frame_list = []
        self.last_chunk_sentence = ""
        self.in_recognize = False


async def heart_beat(websocket: WebSocket):
    while 1:
        await asyncio.sleep(5)
        await websocket.send_json({
            "type": "heartBeat",
            "text": "心跳信息无需理会",
            "language": ""
    })


def is_vad(audio_in, cache, is_final, conn):
    start=time.time()
    audio_int16 = np.frombuffer(audio_in, dtype=np.int16)
    res = conn.firered_vad.process_stream(audio_int16, CHUNK_SIZE // 2)
    return res


async def qwen3_asr_vllm(file_path: str, conn: ConnectionObjectCustomVadV2, websocket: WebSocket):
    try:
        conn.in_recognize = True
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='audio.wav', content_type='audio/wav')
                async with session.post("http://192.168.1.52:8841/v1/asr?key_hopesen=erjt@7", data=data) as _resp:
                    resp = await _resp.json()
                    # result = resp["data"]
                    # language = resp["language"]
                    # return {"code": 200, "data": result, "language": language}
                    if resp["data"]:
                        trans_res = {
                            "type": "transcription",
                            "text": resp["data"],
                            "language": resp["language"]
                        }
                        await websocket.send_json(trans_res)
                    else:
                        await websocket.send_json({
                                "type": "invalid",
                                "text": "语音识别结果为空",
                                "language": ""
                            })
            # await asyncio.sleep(1)
            conn.in_recognize = False
    except Exception as e:
        print_log(f"qwen3-asr error: {e}")
        conn.in_recognize = False
        

def sensevoice_chunk_rec(audio_data):
    start_time = time.perf_counter()
    res = model_asr.generate(audio_data, language="zh")
    print_log(f"chunk res is {res}")
    text = re.sub(r"<\|.*?\|>", "", res[0]["text"]).strip()
    # text = rich_transcription_postprocess(res[0]["text"])
    print_log(f"sensevoice total cost time {time.perf_counter() - start_time} seconds")
    return text


async def req_online_asr(data, is_end: bool, websocket: WebSocket, conn: ConnectionObjectCustomVadV2):
    data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / np.power(2, 15)
    rec_result = await asyncio.to_thread(sensevoice_chunk_rec, data)
    if rec_result:
        if not conn.last_chunk_sentence:
            conn.last_chunk_sentence = rec_result
            message = \
            {
                "type": "chunk",
                # "text": rec_result["text"]["text"],
                "text": rec_result,
                "language": ""
            }
            await websocket.send_json(message)
        else:
            if rec_result != conn.last_chunk_sentence:
                message = \
                {
                    "type": "chunk",
                    # "text": rec_result["text"]["text"],
                    "text": rec_result,
                    "language": ""
                }
                conn.last_chunk_sentence = rec_result
                await websocket.send_json(message)
        


async def receive_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomVadV2):
    while True:
        # data = await websocket.receive()
        data = await websocket.receive_bytes()
        conn.audio_buffer.append(data)
        conn.buffer_size += len(data)

        # robotasr_logger.info(len(data), " ", type(data))
        while conn.buffer_size >= CHUNK_SIZE:
            # 收集足够的数据
            chunk = bytearray()
            remaining = CHUNK_SIZE
            
            while remaining > 0 and conn.audio_buffer:
                first_chunk = conn.audio_buffer[0]
                if len(first_chunk) <= remaining:
                    chunk.extend(conn.audio_buffer.popleft())
                    conn.buffer_size -= len(first_chunk)
                    remaining -= len(first_chunk)
                else:
                    # 只取需要的部分
                    chunk.extend(first_chunk[:remaining])
                    # 更新剩余部分
                    conn.audio_buffer[0] = first_chunk[remaining:]
                    conn.buffer_size -= remaining
                    remaining = 0
            
            # 存储960字节的chunk
            if len(chunk) == CHUNK_SIZE:
                conn.audio_chunk_queue.put(chunk)


async def recog_audio_data(websocket: WebSocket, conn: ConnectionObjectCustomVadV2):
    while True:
        if conn.audio_chunk_queue.empty(): await asyncio.sleep(0.001);continue
        pcm_frame = conn.audio_chunk_queue.get()
        if conn.in_recognize:  continue  # 语音识别中，停止接收数据
        conn.client_audio_buffer.extend(pcm_frame)  # 将新数据加入缓冲区
        while len(conn.client_audio_buffer) >= CHUNK_SIZE:
            # print_log("开始处理音频")
            # silence_duration = time.time() - conn.all_silence_duration  # 累加静默时长
            # # print_log(f"keep silence time: {manager.all_silence_duration[conn.uid] / 1000:.2f} seconds")
            # # 检查是否超过指定时间无人声
            # if silence_duration >= 600000:  # 600000毫秒 = 10分钟
            #     print_log(f"{conn.uid} {silence_duration} 超过{600000 }秒未检测到人声，断开连接")
            #     message = {
            #         "mode": "online",
            #         "text": f"超过 {600000} 秒无人声，已断开连接"
            #     }
            #     await websocket.send_json(message)
            #     await websocket.close(code=1000, reason="silence timeout")
            #     raise TimeoutError("connection break")

            # try:
            if 1:
                chunk = bytes(conn.client_audio_buffer[: CHUNK_SIZE])
                conn.client_audio_buffer = conn.client_audio_buffer[CHUNK_SIZE :]
                # conn.frame_count += 1
                chunk_vad_res = is_vad(chunk, conn.all_cache, False, conn)
                if conn.collect_previous:
                    conn.previous_frame.enqueue(chunk)
                if chunk_vad_res.confidence > conn.vad_max_thre:
                    is_voice = True
                elif chunk_vad_res.confidence < conn.vad_min_thre:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice
                # 声音没低于最低值则延续前一个状态，判断为有声音
                conn.last_is_voice = is_voice
                # 更新滑动窗口
                conn.client_voice_window.append(is_voice)
                client_have_voice = (conn.client_voice_window.count(True) >= conn.frame_window_threshold)
                # 如果之前有声音，但本次没有声音，且与上次有声音的时间差已经超过了静默阈值，则认为已经说完一句话
                if conn.client_have_voice and not client_have_voice:
                    # print_log(f"当前处于尾音判断阶段，当前音频vad置信度：{chunk_vad_res.confidence}")
                    stop_duration = time.time() * 1000 - conn.last_activity_time
                    if stop_duration >= conn.silence_threshold_ms:
                        await websocket.send_json({
                            "type": "vad_stop",
                            "text": "停止监听",
                            "language": ""
                    })
                        file_path = os.path.join("../../temp", f"{str(uuid.uuid4())}.wav")
                        pcm_data = conn.previous_frame_list + conn.all_asr_data
                        with wave.open(file_path, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)  # 2 bytes = 16-bit
                            wf.setframerate(16000)
                            wf.writeframes(b"".join(pcm_data))
                        conn.client_voice_stop = True
                        conn.collect_previous = True
                        conn.client_have_voice = False
                        conn.all_asr_data = []
                        conn.all_point = 0
                        conn.previous_frame_list = []
                        conn.last_chunk_sentence = ""
                        conn.client_voice_window.clear()
                        # resp = await qwen3_asr_vllm(file_path, conn, websocket)
                        asyncio.create_task(qwen3_asr_vllm(file_path, conn, websocket))
                if client_have_voice:
                    conn.collect_previous = False
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000
                    conn.all_point += 1
                    # conn.linear_contiguous_queue.append(conn.frame_count)
                if conn.client_have_voice:
                    conn.all_asr_data.append(chunk)
                    if len(conn.all_asr_data) % 30 == 0:
                        # 进行实时语音识别
                        audio_in = b"".join(conn.previous_frame_list + conn.all_asr_data)
                        asyncio.create_task(req_online_asr(audio_in, False, websocket, conn))
                if conn.all_point == 1:
                    conn.collect_previous = False
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000
                    conn.all_point += 1
                    conn.previous_frame_list = conn.previous_frame.get_all_items()
                    await websocket.send_json({
                            "type": "vad_start",
                            "text": "开始监听",
                            "language": ""
                    })
            # except Exception as e:
            #     print_log("Exception_recog_audio_data:", e)
            #     print_log("vad error")


@app.websocket("/recognition")
async def websocket_endpoint(websocket: WebSocket, uid: str, token: str):
    await websocket.accept()
    # new object
    try:
        prompt = await websocket.receive_json()
        
        # conn = ConnectionObjectCustomVadV2(uid, "", prompt.get("vad_max_thre", 0.9), prompt.get("vad_min_thre", 0.65), prompt.get("silence_threshold_ms", 1500), prompt.get("use_aed", False))
        conn = ConnectionObjectCustomVadV2(uid, "", prompt.get("vad_max_thre", 0.9), prompt.get("vad_min_thre", 0.65), prompt.get("silence_threshold_ms", 2200), prompt.get("use_aed", False))
        print_log(f"输入的uid是 {conn.uid}")
        await asyncio.gather(
            heart_beat(websocket),
            receive_audio_data(websocket, conn),
            recog_audio_data(websocket, conn),
        )
    except ValueError as e:
        await websocket.close(reason="API key error")
        logging.error(f"catch error {e}")
    except Exception as e:
        conn.firered_vad.destroy()
        conn.firered_vad = None
        print_log(f"catch error {e}")
        print_log(f"剩余的CHUNK SIZE {conn.buffer_size}")
        print_log(f"{conn.uid}缓存清理完成")
        

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=18113)