import os
import time
import asyncio
import uvicorn
import sherpa_onnx
import numpy as np
import soundfile as sf
from queue import Queue
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sherpa_onnx import OfflineRecognizer, SileroVadModelConfig, VadModelConfig, VoiceActivityDetector

app = FastAPI()

recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
model="../../models/sherpa-onnx-sense-voice/model.onnx",
tokens="../../models/sherpa-onnx-sense-voice/tokens.txt",
provider="cuda",
num_threads=2,
use_itn=True,
sample_rate=16000,
debug=False
)

wave_filename = "../..//models/SenseVoiceSmall/example/zh.mp3"
a, sample_rate = sf.read(wave_filename, dtype="int16", always_2d=True)
# audio = audio[:, 0]  # only use the first channel
# audio is a 1-D float32 numpy array normalized to the range [-1, 1]
# sample_rate does not need to be 16000 Hz
stream = recognizer.create_stream()
stream.accept_waveform(sample_rate, a)
recognizer.decode_stream(stream)
print(wave_filename)
print(stream.result)


def stt(audio):
    start_time = time.perf_counter()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, np.frombuffer(audio, dtype=np.int16))
    recognizer.decode_stream(stream)
    print(f"流式语音识别结果：{stream.result.text} | 耗时：{time.perf_counter() - start_time} 秒")
    return stream.result.text, stream.result.lang
    

async def receive_audio(websocket: WebSocket, q: Queue):
    while 1:
        audio = await websocket.receive_bytes()
        q.put(audio)
        await asyncio.sleep(0.005)
    

async def send_stt_res(websocket: WebSocket, q: Queue):
    while 1:
        if not q.empty():
            audio = q.get()
            rec_result, language = await asyncio.to_thread(stt, audio)
            await websocket.send_json({
                "type": "chunk",
                "text": rec_result,
                "language": language
            })
        else:
            await asyncio.sleep(0.01)


@app.websocket("/v1/stream/chunk")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    q = Queue()
    try:
        await asyncio.gather(
            receive_audio(websocket, q),
            send_stt_res(websocket, q)
        )
    except WebSocketDisconnect:
        print(f"manba out")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=18113)