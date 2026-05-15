"""
Plan Engine
定义会话的执行计划（Step 序列）
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class StepStatus(Enum):
    """Step 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """计划中的一个步骤"""
    tool_name: str
    input_context: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    attempts: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class Plan:
    """执行计划"""
    session_id: str
    steps: List[Step]
    current_step_index: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)
    
    @property
    def has_failed(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)
    
    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed / len(self.steps)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_step": self.current_step_index,
            "total_steps": len(self.steps),
            "progress": self.progress,
            "is_complete": self.is_complete,
            "has_failed": self.has_failed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "status": s.status.value,
                    "attempts": s.attempts,
                    "error": s.error,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                }
                for s in self.steps
            ]
        }


# ─────────────────────────────────────────────
# 预定义 Plan 模板（工厂函数）
# ─────────────────────────────────────────────

def plan_after_drawing(session_id: str) -> Plan:
    """绘画提交后的执行计划"""
    return Plan(session_id=session_id, steps=[
        Step(tool_name="AnalyzeDrawingTool", input_context={"stream": True}),
    ])


def plan_after_answers(session_id: str) -> Plan:
    """用户回答后的执行计划"""
    return Plan(session_id=session_id, steps=[
        Step(tool_name="GenerateImageTool", input_context={"do_warmup": True}),
    ])


def plan_after_selection(session_id: str) -> Plan:
    """图像选择后的执行计划"""
    return Plan(session_id=session_id, steps=[
        Step(tool_name="AskFollowUpTool"),
    ])


def plan_after_final_answers(session_id: str) -> Plan:
    """最终回答后的执行计划"""
    return Plan(session_id=session_id, steps=[
        Step(tool_name="GenerateReportTool"),
    ])
