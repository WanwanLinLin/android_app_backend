from typing import Optional


def extract_json_from_response(response: str) -> Optional[str]:
        """
        从响应中提取 JSON 字符串
        
        Args:
            response: 模型响应内容
        
        Returns:
            JSON 字符串，如果提取失败则返回 None
        """
        json_str = None
        
        # 方法1: 查找 JSON 代码块
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            if json_end > json_start:
                json_str = response[json_start:json_end].strip()
        elif "```" in response:
            # 查找第一个代码块
            json_start = response.find("```") + 3
            json_end = response.find("```", json_start)
            if json_end > json_start:
                json_str = response[json_start:json_end].strip()
                # 移除语言标识（如 "json"）
                lines = json_str.split('\n', 1)
                if len(lines) > 1 and lines[0].strip().lower() in ['json', 'javascript']:
                    json_str = lines[1]
        
        # 方法2: 尝试查找 JSON 对象
        if not json_str:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
        
        # 方法3: 如果仍然没有找到，尝试清理响应并查找 JSON
        if not json_str:
            # 移除常见的 Markdown 格式标记
            cleaned = response.replace("**", "").replace("*", "").strip()
            json_start = cleaned.find("{")
            json_end = cleaned.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned[json_start:json_end]
        
        return json_str