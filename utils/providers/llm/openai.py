import httpx
import openai
from openai.types import CompletionUsage
from utils.providers.llm.base import LLMProviderBase
from utils.getLogs import LOG


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.model_name = config.get("params").get("model_name")
        self.api_key = config.get("apikey")
        if "base_url" in config.get("params"):
            self.base_url = config.get("params").get("base_url")
        else:
            self.base_url = config.get("url")
        # 增加timeout的配置项，单位为秒
        timeout = config.get("timeout", 300)
        self.timeout = int(timeout) if timeout else 300

        param_defaults = {
            "max_tokens": (500, int),
            "temperature": (0.7, lambda x: round(float(x), 1)),
            "top_p": (1.0, lambda x: round(float(x), 1)),
            "frequency_penalty": (0, lambda x: round(float(x), 1)),
        }

        for param, (default, converter) in param_defaults.items():
            value = config.get(param)
            try:
                setattr(
                    self,
                    param,
                    converter(value) if value not in (None, "") else default,
                )
            except (ValueError, TypeError):
                setattr(self, param, default)

        LOG(f"意图识别参数初始化: {self.temperature}, {self.max_tokens}, {self.top_p}, {self.frequency_penalty}", "DEBUG")

        self.client = openai.AsyncClient(api_key=self.api_key, base_url=self.base_url, timeout=httpx.Timeout(self.timeout))

    async def response(self, session_id, dialogue, **kwargs):
        try:
            print(f"dialogue is {dialogue}")
            responses = await self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                frequency_penalty=kwargs.get(
                    "frequency_penalty", self.frequency_penalty
                ),
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            is_active = True
            async for chunk in responses:
                try:
                    # 检查是否存在有效的choice且content不为空
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = delta.content if hasattr(delta, "content") else ""
                    # if not content:
                    #     content = delta.reasoning_content if hasattr(delta, "reasoning_content") else ""
                except IndexError:
                    content = ""
                if content:
                    # 处理标签跨多个chunk的情况
                    if "<think>" in content:
                        is_active = False
                        content = content.split("<think>")[0]
                    if "</think>" in content:
                        is_active = True
                        content = content.split("</think>")[-1]
                    if is_active:
                        yield content

        except Exception as e:
            LOG(f"Error in response generation: {e}", "DEBUG")

    async def response_with_functions(self, session_id, dialogue, **kwargs):
        try:
            stream = await self.client.chat.completions.create(
                model=self.model_name, messages=dialogue, stream=True, tools=kwargs["functions"]
            )

            async for chunk in stream:
                # 检查是否存在有效的choice且content不为空
                if getattr(chunk, "choices", None):
                    # yield chunk.choices[0].delta.content, chunk.choices[
                    #     0
                    # ].delta.tool_calls
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = delta.content if hasattr(delta, "content") else ""
                    # if not content:
                    #     content = delta.reasoning_content if hasattr(delta, "reasoning_content") else ""
                    yield content, chunk.choices[
                        0
                    ].delta.tool_calls
                # 存在 CompletionUsage 消息时，生成 Token 消耗 log
                elif isinstance(getattr(chunk, "usage", None), CompletionUsage):
                    usage_info = getattr(chunk, "usage", None)

        except Exception as e:
            yield f"【OpenAI服务响应异常: {e}】", None
