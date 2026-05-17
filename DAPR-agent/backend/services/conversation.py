"""
对话历史管理器 - 支持长上下文
"""
from datetime import datetime
from typing import Dict, List


class ConversationManager:
    """对话历史管理器 - 支持长上下文"""

    def __init__(self, max_context_length: int = 32000, max_keep_turns: int = 20):
        self.max_context_length = max_context_length
        self.max_keep_turns = max_keep_turns
        self.messages = []
        self.summary = ""

    def add_message(self, role: str, content: str):
        """添加消息到历史"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

        if len(self.messages) > self.max_keep_turns:
            self._compress_history()

    def _compress_history(self):
        """压缩历史对话"""
        recent_messages = self.messages[-10:]
        older_messages = self.messages[:-10]
        if older_messages:
            key_points = []
            for msg in older_messages:
                if msg["role"] == "user":
                    key_points.append(f"用户提到: {msg['content'][:50]}...")
                elif msg["role"] == "assistant":
                    key_points.append(f"AI回应: {msg['content'][:50]}...")
            self.summary = "\n".join(key_points[-5:])

        self.messages = recent_messages

    def get_messages(self, include_summary: bool = True) -> List[Dict]:
        """获取格式化的消息列表"""
        result = []
        if include_summary and self.summary:
            result.append({
                "role": "system",
                "content": f"【对话历史摘要】\n{self.summary}"
            })

        for msg in self.messages:
            result.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        return result

    def clear(self):
        """清空对话历史"""
        self.messages = []
        self.summary = ""
