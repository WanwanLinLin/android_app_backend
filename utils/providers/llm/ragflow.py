import json
import httpx
import openai
import aiohttp
from openai.types import CompletionUsage
from utils.providers.llm.base import LLMProviderBase
from utils.getLogs import LOG


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.api_key = config.get("apikey")
        self.session_id = None
        self.url = config.get("url")
        self.headers = {
            # Already added when you pass json= but not when you pass data=
            'Content-Type': 'application/json',
            'Authorization': self.api_key,
        }
        self.params = config.get("params")

    async def create_session(self):
        json_data = {
            "question": "你是我的，我是你的谁？",
            "stream": False
        }
        if self.params:
            json_data.update(self.params)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120), connector=aiohttp.TCPConnector(ssl=False, limit=1024*1024*100), read_bufsize=1024 * 1024 * 5) as session:
            async with session.post(self.url, headers=self.headers, json=json_data) as response:
                res = await response.json()
                session_id = res["data"]["session_id"]
                self.session_id = session_id
    
    async def response(self, session_id, dialogue, **kwargs):
        if not self.session_id:
            await self.create_session()
            LOG(f"ragflow 成功创建新的session_id: {self.session_id}")
        reply_reply_prefix = ""
        json_data = {
            "question": dialogue[-1]["content"],
            "stream": True,
            "session_id": self.session_id
        }
        if self.params:
            json_data.update(self.params)
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
                                data_dict = json.loads(json_str)
                                if 'data' in data_dict and data_dict['data']!=True and  'answer' in data_dict['data']:
                                    if "running_status" in data_dict['data']: continue  # 不显示插件检索部分
                                    # print("data_dict['data'] is ", data_dict['data'])
                                    if data_dict["code"] == 500:
                                        output = "知识库未找到答案！"
                                    else:
                                        output = data_dict['data']['answer']
                                    # if "is running..." in output: continue      # 不显示插件检索部分
                                    _output = output
                                    # 妥善处理前缀部分
                                    if reply_reply_prefix not in output:
                                        break
                                    output = output.replace(reply_reply_prefix, "")
                                    reply_reply_prefix = _output
                                    yield output
                                    # yield [data_dict['data']['answer'],session_id]
                            except:
                                pass
                else:
                    LOG(f"Error in ragflow response generation: {await response.content.read()}", "DEBUG")

