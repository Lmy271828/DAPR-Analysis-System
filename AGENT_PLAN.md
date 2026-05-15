# Agent 架构重构计划（务实版）

> **编制日期**: 2026-05-15  
> **前置状态**: Phase 1 ✅ | Phase 2 ✅ | 图像并行化 ✅  
> **目标**: 将硬编码后台任务升级为可编排的 Agent 工具链，支持失败恢复、执行追踪、条件分支

---

## 一、当前问题诊断

### 1.1 硬编码任务的问题

```python
# main.py 当前模式
background_tasks.add_task(analyze_drawing_task_stream, session_id)
# → 分析完成后自动推送 questions，但失败时无恢复机制

background_tasks.add_task(generate_images_task, session_id)
# → 图像生成失败时，整个会话卡住

background_tasks.add_task(final_analysis_task, session_id)
# → 与 generate_final_report_task 之间无显式依赖管理
```

| 问题 | 影响 |
|------|------|
| **失败即终止** | 任一任务失败，整个会话流程中断 |
| **无重试机制** | LLM API 偶发超时，用户需手动刷新 |
| **无执行追踪** | 不知道当前会话卡在哪一步 |
| **紧耦合** | 任务逻辑和 FastAPI 路由深度绑定 |
| **无法扩展** | 新增阶段需要修改 main.py 多处 |

### 1.2 不做的事（明确边界）

- ❌ **LLM 做决策的 ReAct Loop**：过度复杂，当前状态机已够用
- ❌ **多 Agent 协作**：单用户会话不需要多 Agent
- ❌ **Tool Calling 标准协议**：不需要兼容 OpenAI Function Calling 格式
- ❌ **向量记忆/ChromaDB**：SQLite 已足够

---

## 二、核心设计：轻量级 Tool + Plan 模式

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Request                         │
│  (POST /analyze, /answers, /select, /final-answers)         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Session    │  │  Plan       │  │  Tool       │        │
│  │  Registry   │──│  Engine     │──│  Registry   │        │
│  │  (dict)     │  │  (step by   │  │  (5 tools)  │        │
│  └─────────────┘  │  step)      │  └─────────────┘        │
│                   └─────────────┘                          │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Analyze  │   │ Generate │   │ Finalize │
   │ Tool     │   │ Tool     │   │ Tool     │
   └──────────┘   └──────────┘   └──────────┘
```

### 2.2 核心概念

| 概念 | 说明 | 类比 |
|------|------|------|
| **Tool** | 一个可执行的原子任务（分析绘画、生成图像、提问等） | Makefile target |
| **Plan** | 当前会话的执行计划，由有序 Step 组成 | CI/CD pipeline |
| **Step** | Plan 中的一个节点，包含 tool_name、input、retry_policy | GitHub Actions step |
| **Execution State** | 记录 Plan 的执行进度（completed_steps, current_step, errors） | Jenkins build status |

---

## 三、Task 清单与排期

### Task 1: Tool Registry 框架（Week 1，2 天）

**新增文件**: `DAPR-agent/backend/agent/tools.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ToolResult:
    success: bool
    output: Any
    error: Optional[str] = None
    retryable: bool = False  # 是否可重试

class BaseTool(ABC):
    name: str
    max_retries: int = 3
    timeout: int = 300
    
    @abstractmethod
    async def execute(self, session_id: str, context: Dict) -> ToolResult:
        pass
    
    async def run_with_retry(self, session_id: str, context: Dict) -> ToolResult:
        for attempt in range(self.max_retries):
            result = await self.execute(session_id, context)
            if result.success:
                return result
            if not result.retryable or attempt == self.max_retries - 1:
                return result
            await asyncio.sleep(2 ** attempt)  # 指数退避
        return result
```

**5 个具体 Tool**:

| Tool | 对应原函数 | 职责 |
|------|-----------|------|
| `AnalyzeDrawingTool` | `analyze_drawing_task_stream` | 流式分析绘画，生成问题和假设 |
| `GenerateImageTool` | `generate_images_task` | 异步生成 3 张图像变体 |
| `AskFollowUpTool` | `final_analysis_task` | 根据选择生成深入问题 |
| `GenerateReportTool` | `generate_final_report_task` | 生成最终艺术探索报告 |
| `NotifyUserTool` | (分散在多处) | 通过 WebSocket 推送状态更新 |

**修改文件**:
- `main.py`：删除 4 个 `background_tasks.add_task(...)` 硬编码函数
- `main.py`：路由函数改为调用 `AgentOrchestrator.submit_plan(session_id, plan)`

---

### Task 2: Plan Engine 执行引擎（Week 1，2 天）

**新增文件**: `DAPR-agent/backend/agent/plan.py`

```python
from typing import List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class Step:
    tool_name: str
    input_context: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    attempts: int = 0

@dataclass
class Plan:
    session_id: str
    steps: List[Step]
    current_step_index: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)
    
    @property
    def has_failed(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)
```

**Plan 模板定义**（预定义 3 种执行流程）：

```python
# 流程 1：绘画提交后
PLAN_AFTER_DRAWING = [
    Step(tool_name="AnalyzeDrawingTool", input_context={"stream": True}),
    Step(tool_name="NotifyUserTool", input_context={"message_type": "questions"}),
]

# 流程 2：用户回答后
PLAN_AFTER_ANSWERS = [
    Step(tool_name="GenerateImageTool", input_context={"warmup": True}),
    Step(tool_name="NotifyUserTool", input_context={"message_type": "generated_images"}),
]

# 流程 3：图像选择后
PLAN_AFTER_SELECTION = [
    Step(tool_name="AskFollowUpTool"),
    Step(tool_name="NotifyUserTool", input_context={"message_type": "final_questions"}),
]

# 流程 4：最终回答后
PLAN_AFTER_FINAL_ANSWERS = [
    Step(tool_name="GenerateReportTool"),
    Step(tool_name="NotifyUserTool", input_context={"message_type": "final_report"}),
]
```

---

### Task 3: Agent Orchestrator 编排器（Week 1，1 天）

**新增文件**: `DAPR-agent/backend/agent/orchestrator.py`

```python
class AgentOrchestrator:
    """轻量级编排器：顺序执行 Plan，支持失败恢复"""
    
    def __init__(self):
        self.plans: Dict[str, Plan] = {}          # session_id -> Plan
        self.running: Dict[str, asyncio.Task] = {} # session_id -> Task
        self.tool_registry: Dict[str, BaseTool] = {}
    
    def register_tool(self, tool: BaseTool):
        self.tool_registry[tool.name] = tool
    
    async def submit_plan(self, session_id: str, plan: Plan):
        """提交执行计划"""
        self.plans[session_id] = plan
        if session_id in self.running:
            self.running[session_id].cancel()
        task = asyncio.create_task(self._execute_plan(session_id))
        self.running[session_id] = task
    
    async def _execute_plan(self, session_id: str):
        """顺序执行 Plan 的每个 Step"""
        plan = self.plans[session_id]
        
        while plan.current_step_index < len(plan.steps):
            step = plan.steps[plan.current_step_index]
            tool = self.tool_registry.get(step.tool_name)
            
            if not tool:
                step.status = StepStatus.FAILED
                step.error = f"Tool {step.tool_name} not found"
                break
            
            step.status = StepStatus.RUNNING
            step.attempts += 1
            
            # 执行 Tool（带重试）
            result = await tool.run_with_retry(session_id, step.input_context)
            
            if result.success:
                step.status = StepStatus.COMPLETED
                step.output = result.output
                plan.current_step_index += 1
            elif step.attempts >= tool.max_retries:
                step.status = StepStatus.FAILED
                step.error = result.error
                # 失败策略：标记失败但继续执行后续步骤（除非是关键步骤）
                if step.tool_name in ("AnalyzeDrawingTool", "GenerateReportTool"):
                    break  # 关键步骤失败，终止 Plan
                plan.current_step_index += 1  # 非关键步骤，跳过继续
            
            # 保存执行状态到数据库
            await self._persist_state(session_id)
        
        # Plan 完成或失败，清理
        self.running.pop(session_id, None)
    
    async def _persist_state(self, session_id: str):
        """将 Plan 执行状态持久化到数据库"""
        plan = self.plans.get(session_id)
        if plan:
            session = Session.load(session_id)
            if session:
                session.agent_state = {
                    "plan": plan.to_dict(),
                    "updated_at": datetime.now().isoformat()
                }
                session.save()
```

---

### Task 4: 执行状态可视化（Week 2，2 天）

**目标**: 在咨询师面板显示当前会话的 Agent 执行进度。

**新增 WebSocket 消息类型**:

```json
{
  "type": "agent_state",
  "data": {
    "session_id": "xxx",
    "current_step": 2,
    "total_steps": 4,
    "step_name": "GenerateImageTool",
    "step_status": "running",
    "completed_steps": ["AnalyzeDrawingTool", "NotifyUserTool"],
    "failed_steps": [],
    "estimated_time": "15s"
  }
}
```

**前端修改**:
- `components/session-detail.js`: 在会话详情面板增加"执行进度"区块
- 显示步骤条（Stepper UI）：分析 → 提问 → 生成图像 → 选择 → 最终问题 → 报告
- 实时高亮当前执行中的步骤

---

### Task 5: 历史 Plan 重放（Week 2，1 天）

**场景**: 用户断线后重连，或咨询师想查看某会话的执行过程。

**实现**:
- Plan 执行历史保存到数据库 `agent_executions` 表
- 新增 API: `GET /api/session/{id}/execution-history`
- 前端可查看每个 Step 的执行时间、输入输出、错误信息

---

## 四、排期

```
Week 1 (5/15-5/22):
  Day 1-2: Task 1 — Tool Registry 框架 + 5 个 Tool 实现
  Day 3-4: Task 2 — Plan Engine 执行引擎 + Plan 模板
  Day 5:   Task 3 — Agent Orchestrator 编排器

Week 2 (5/22-5/29):
  Day 1-2: Task 4 — 执行状态可视化（前端 Stepper UI）
  Day 3:   Task 5 — 历史 Plan 重放
  Day 4-5: 集成测试 + 修复
```

---

## 五、接口兼容性

| 现有接口 | 变更 | 影响 |
|---------|------|------|
| `POST /api/session/{id}/analyze` | 内部改为 `orchestrator.submit_plan(..., PLAN_AFTER_DRAWING)` | 无前端影响 |
| `POST /api/session/{id}/answers` | 内部改为 `orchestrator.submit_plan(..., PLAN_AFTER_ANSWERS)` | 无前端影响 |
| `POST /api/session/{id}/select` | 内部改为 `orchestrator.submit_plan(..., PLAN_AFTER_SELECTION)` | 无前端影响 |
| `POST /api/session/{id}/final-answers` | 内部改为 `orchestrator.submit_plan(..., PLAN_AFTER_FINAL_ANSWERS)` | 无前端影响 |
| WebSocket `agent_state` | **新增** | 前端可选接入 |

**底线承诺**: 所有现有前端代码无需修改即可正常运行。

---

## 六、验收标准

| 检查项 | 标准 |
|--------|------|
| 失败恢复 | LLM API 超时后自动重试 3 次，最终失败时前端收到明确错误通知 |
| 执行追踪 | 咨询师面板可实时查看每个会话的执行步骤和进度 |
| 断线恢复 | 用户刷新页面后，可恢复到正确的会话状态（基于数据库中的 Plan 状态） |
| 并发安全 | 10 个用户同时提交，Plan 互不干扰，数据库无冲突 |
| 向后兼容 | 现有所有 API 和 WebSocket 消息格式不变 |

---

*文档版本: 1.0*  
*最后更新: 2026-05-15*
