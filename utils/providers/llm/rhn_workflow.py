import json
import time
import httpx
import openai
import aiohttp
from openai.types import CompletionUsage
from utils.providers.llm.base import LLMProviderBase
from utils.getLogs import LOG


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.api_key = config.get("apikey")
        self.url = config.get("url")
        self.headers = config.get("params").get("headers")
        self.params = config.get("params")
    
    async def response(self, session_id, dialogue, **kwargs):
        pkg_nums = 0
        start_time = time.perf_counter()
        reply_reply_prefix = ""
        json_data = {
            "session_id": session_id,
            "event": "chat",
            "text": dialogue[-1]["content"],
            "stream": True
        }
        json_data = json.dumps(json_data)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120), connector=aiohttp.TCPConnector(ssl=False, limit=1024*1024*100)) as session:
            async with session.post(self.url, headers=self.headers, data=json_data) as response:
                if response.status == 200:
                    # 遍历响应内容
                    async for chunk in response.content:
                        if chunk:
                            try:
                                decoded_data = chunk.decode('utf-8')
                                # print(f"rag origin string: {decoded_data[:100]}")
                                # 查找 JSON 数据部分
                                json_str = decoded_data.split('data:')[1].strip()
                                output = json.loads(json_str)
                                if "done" in output and output["done"]: break
                                yield output["delta"]
                                    # yield [data_dict['data']['answer'],session_id]
                            except Exception as e:
                                pass
                else:
                    LOG(f"Error in ragflow response generation: {await response.content.read()}", "DEBUG")

