"""
Tool Registry
将现有后台任务封装为可重试、可追踪的 Tool
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Tool 执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    retryable: bool = False


class BaseTool(ABC):
    """Tool 基类"""
    name: str = ""
    max_retries: int = 3
    timeout: int = 300
    
    @abstractmethod
    async def execute(self, session_id: str, context: Dict[str, Any]) -> ToolResult:
        """执行 Tool，子类必须实现"""
        pass
    
    async def run_with_retry(self, session_id: str, context: Dict[str, Any]) -> ToolResult:
        """带重试的执行"""
        for attempt in range(self.max_retries):
            try:
                result = await asyncio.wait_for(
                    self.execute(session_id, context),
                    timeout=self.timeout
                )
                if result.success:
                    return result
                if not result.retryable or attempt == self.max_retries - 1:
                    return result
                await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                if attempt == self.max_retries - 1:
                    return ToolResult(
                        success=False,
                        error=f"Timeout after {self.timeout}s",
                        retryable=False
                    )
                await asyncio.sleep(2 ** attempt)
        return ToolResult(success=False, error="Max retries exceeded", retryable=False)


class ToolWrapper(BaseTool):
    """
    将现有 async 函数包装为 Tool。
    用于快速迁移现有后台任务，无需重写业务逻辑。
    """
    def __init__(
        self,
        name: str,
        func: Callable[[str], Awaitable[Any]],
        max_retries: int = 3,
        timeout: int = 300,
        retryable_exceptions: tuple = (TimeoutError, ConnectionError)
    ):
        self.name = name
        self.func = func
        self.max_retries = max_retries
        self.timeout = timeout
        self.retryable_exceptions = retryable_exceptions
    
    async def execute(self, session_id: str, context: Dict[str, Any]) -> ToolResult:
        try:
            # 如果 func 不接受 context，只传 session_id
            import inspect
            sig = inspect.signature(self.func)
            if len(sig.parameters) == 1:
                await self.func(session_id)
            else:
                await self.func(session_id, **context)
            return ToolResult(success=True, output=None)
        except self.retryable_exceptions as e:
            return ToolResult(success=False, error=str(e), retryable=True)
        except Exception as e:
            return ToolResult(success=False, error=str(e), retryable=False)


class NotifyUserTool(BaseTool):
    """
    通用通知 Tool。
    用于 Plan 中需要显式推送状态更新的步骤。
    """
    name = "NotifyUserTool"
    max_retries = 1
    
    def __init__(self, manager=None):
        self._manager = manager
    
    async def execute(self, session_id: str, context: Dict[str, Any]) -> ToolResult:
        message_type = context.get("message_type")
        if not message_type:
            return ToolResult(success=False, error="message_type required")
        
        if self._manager is None:
            return ToolResult(success=False, error="WebSocket manager not available")
        
        try:
            if message_type == "agent_state":
                await self._manager.send_to_subject(session_id, {
                    "type": "agent_state",
                    "data": context.get("state", {})
                })
            return ToolResult(success=True)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
