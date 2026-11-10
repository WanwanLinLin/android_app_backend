from typing import List
from abc import ABC, abstractmethod

from utils.common.enumTaskType import WebsocketServerEvent


async def notify_client_error(conn, msg: str):
    """大模型报错时向终端推送 assistant 事件（与正常回复同型，终端无需新增处理）：
    {"type": "assistant", "text": 报错提示}。
    conn 由对话模板调用 response() 时以 kwargs 传入；离线调用
    （response_no_stream 等）可能没有 conn 或 conn.websocket，全部静默跳过，
    推送本身失败（如连接已断开）也不能再把异常抛回 LLM 流。"""
    websocket = getattr(conn, "websocket", None) if conn is not None else None
    if websocket is None:
        return
    try:
        await websocket.send_json({"type": WebsocketServerEvent.ASSISTANT.value, "text": msg})
    except Exception:
        pass


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