"""
Agent Orchestrator
轻量级编排器：顺序执行 Plan，支持失败恢复和状态持久化
"""
import asyncio
from typing import Dict, Optional
from datetime import datetime

from .tools import BaseTool
from .plan import Plan, Step, StepStatus


class AgentOrchestrator:
    """
    会话级 Agent 编排器。
    
    每个会话同一时间只能有一个 Plan 在执行。
    Plan 失败时，关键 Tool 会终止流程，非关键 Tool 会跳过继续。
    """
    
    # 关键 Tool：失败时终止整个 Plan
    CRITICAL_TOOLS = {"AnalyzeDrawingTool", "GenerateReportTool"}
    
    def __init__(self):
        self.plans: Dict[str, Plan] = {}
        self.running: Dict[str, asyncio.Task] = {}
        self.tool_registry: Dict[str, BaseTool] = {}
        self._manager = None  # WebSocket manager，用于推送状态
    
    def set_manager(self, manager):
        """注入 WebSocket manager（用于状态推送）"""
        self._manager = manager
    
    def register_tool(self, tool: BaseTool):
        """注册 Tool"""
        self.tool_registry[tool.name] = tool
    
    async def submit_plan(self, session_id: str, plan: Plan):
        """
        提交执行计划。
        如果该会话已有运行中的 Plan，先取消。
        """
        # 取消旧 Plan
        if session_id in self.running:
            old_task = self.running[session_id]
            if not old_task.done():
                old_task.cancel()
                try:
                    await old_task
                except asyncio.CancelledError:
                    pass
        
        self.plans[session_id] = plan
        task = asyncio.create_task(
            self._execute_plan(session_id),
            name=f"agent-plan-{session_id[:8]}"
        )
        self.running[session_id] = task
        
        print(f"[Agent] Plan 已提交: session={session_id[:8]}..., steps={len(plan.steps)}")
    
    async def _execute_plan(self, session_id: str):
        """顺序执行 Plan 的每个 Step"""
        plan = self.plans.get(session_id)
        if not plan:
            print(f"[Agent] 错误: Plan 不存在 {session_id[:8]}...")
            return
        
        try:
            while plan.current_step_index < len(plan.steps):
                step = plan.steps[plan.current_step_index]
                tool = self.tool_registry.get(step.tool_name)
                
                if not tool:
                    step.status = StepStatus.FAILED
                    step.error = f"Tool '{step.tool_name}' not found"
                    await self._notify_state(session_id, plan)
                    break
                
                # 执行 Step
                step.status = StepStatus.RUNNING
                step.attempts += 1
                step.started_at = datetime.now().isoformat()
                
                print(f"[Agent] 执行 Step {plan.current_step_index + 1}/{len(plan.steps)}: {step.tool_name} (session={session_id[:8]}...)")
                await self._notify_state(session_id, plan)
                
                result = await tool.run_with_retry(session_id, step.input_context)
                
                step.completed_at = datetime.now().isoformat()
                plan.updated_at = step.completed_at
                
                if result.success:
                    step.status = StepStatus.COMPLETED
                    step.output = result.output
                    plan.current_step_index += 1
                    print(f"[Agent] Step 完成: {step.tool_name}")
                else:
                    step.status = StepStatus.FAILED
                    step.error = result.error
                    print(f"[Agent] Step 失败: {step.tool_name} - {result.error}")
                    
                    # 关键 Tool 失败，终止 Plan
                    if step.tool_name in self.CRITICAL_TOOLS:
                        await self._notify_state(session_id, plan)
                        await self._notify_failure(session_id, step)
                        break
                    
                    # 非关键 Tool，跳过继续
                    plan.current_step_index += 1
                
                # 持久化状态
                await self._persist_state(session_id, plan)
                await self._notify_state(session_id, plan)
            
            # Plan 完成
            if plan.is_complete:
                print(f"[Agent] Plan 全部完成: session={session_id[:8]}...")
            elif plan.has_failed:
                print(f"[Agent] Plan 部分失败: session={session_id[:8]}...")
        
        except asyncio.CancelledError:
            print(f"[Agent] Plan 被取消: session={session_id[:8]}...")
            raise
        except Exception as e:
            print(f"[Agent] Plan 执行异常: session={session_id[:8]}... - {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running.pop(session_id, None)
    
    async def _persist_state(self, session_id: str, plan: Plan):
        """将 Plan 执行状态持久化到数据库"""
        try:
            from models import Session
            session = Session.load(session_id)
            if session:
                session.agent_state = plan.to_dict()
                session.save()
        except Exception as e:
            print(f"[Agent] 状态持久化失败: {e}")
    
    async def _notify_state(self, session_id: str, plan: Plan):
        """通过 WebSocket 推送执行状态"""
        if self._manager is None:
            return
        try:
            current_step = plan.steps[plan.current_step_index] if plan.current_step_index < len(plan.steps) else None
            await self._manager.send_to_subject(session_id, {
                "type": "agent_state",
                "data": {
                    "session_id": session_id,
                    "current_step": plan.current_step_index + 1,
                    "total_steps": len(plan.steps),
                    "progress": plan.progress,
                    "step_name": current_step.tool_name if current_step else None,
                    "step_status": current_step.status.value if current_step else None,
                    "is_complete": plan.is_complete,
                    "has_failed": plan.has_failed,
                }
            })
        except Exception:
            pass
    
    async def _notify_failure(self, session_id: str, step: Step):
        """通知用户 Step 失败"""
        if self._manager is None:
            return
        try:
            await self._manager.send_to_subject(session_id, {
                "type": "agent_error",
                "data": {
                    "step": step.tool_name,
                    "error": step.error,
                    "message": f"步骤 '{step.tool_name}' 执行失败，请稍后重试。"
                }
            })
        except Exception:
            pass
    
    def get_plan(self, session_id: str) -> Optional[Plan]:
        """获取会话的当前 Plan"""
        return self.plans.get(session_id)
    
    def is_running(self, session_id: str) -> bool:
        """检查会话是否有运行中的 Plan"""
        task = self.running.get(session_id)
        return task is not None and not task.done()
