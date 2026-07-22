from typing import List
from abc import ABC, abstractmethod


class LLMProviderBase(ABC):
    @abstractmethod
    async def response(self, session_id: str, dialogue: List):
        """LLM response generator"""
        pass

    async def response_no_stream(self, system_prompt: str, user_prompt: str, **kwargs):
        try:
            # 构造对话格式
            dialogue = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            result = ""
            async for part in self.response("", dialogue, **kwargs):
                result += part
            return result

        except Exception as e:
            return "【LLM服务响应异常】"
    
    async def response_with_functions(self, session_id: str, dialogue: List, functions=None):
        """
        Default implementation for function calling (streaming)
        This should be overridden by providers that support function calls

        Returns: generator that yields either text tokens or a special function call token
        """
        # For providers that don't support functions, just return regular response
        async for token in self.response(session_id, dialogue):
            yield token, None