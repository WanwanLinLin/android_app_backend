import json
import httpx
import openai
import aiohttp
from openai.types import CompletionUsage
from utils.providers.llm.base import LLMProviderBase, notify_client_error
from utils.getLogs import LOG


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.name = config.get("desc", "")
        self.model_name = config.get("params").get("model_name")
        self.api_key = config.get("apikey")
        self.response_language = config.get("params").get("response_language", "zh-cn")   # zh-cn, en, zh-hk
        if "base_url" in config:
            self.base_url = config.get("base_url")
        else:
            self.base_url = config.get("url")
        self.body = {
            "role": "manbaout",
            "vr": False,
            "en": False,
            "characters": f"{self.model_name},{self.model_name}",
            "response_language":  self.response_language,
            # "additional_param": {"company_name": "字节跳动"}
        }
        

    async def response(self, session_id, dialogue, **kwargs):
        try:
            if len(dialogue) == 1:
                self.body["mode"] = "start"
                self.body["consultId"] = session_id
                self.body["content"] = ""
            else:
                self.body["mode"] = "chat"
                self.body["consultId"] = session_id
                self.body["content"] = dialogue[-1]["content"]
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=self.body) as _resp:
                    async for line in _resp.content:
                        line = line.decode("UTF-8").strip()
                        if line:
                            if line == "data: [DONE]" or line == " data: [DONE]" or line == "data:[DONE]": break
                            output = json.loads(line[5:])
                            content = output["choices"][0]["delta"]["content"]
                            if content: yield content

        except Exception as e:
            LOG(f"Error in response generation: {e}", "ERROR")
            # 报错提示已由 notify_client_error 以 assistant 事件推送，
            # 不再 yield（否则 monitor 会把它转成第二条 assistant 消息重复下发）
            await notify_client_error(kwargs.get("conn"), f"大模型「{self.name}」回复失败：{e}")

    async def response_with_functions(self, session_id, dialogue, **kwargs):
        try:
            ...

        except Exception as e:
            LOG(f"Error in response_with_functions generation: {e}", "ERROR")
            await notify_client_error(kwargs.get("conn"), f"大模型「{self.name}」回复失败：{e}")
            yield f"【心理对话服务响应异常: {e}】", None
