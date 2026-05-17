"""
InterviewAgent — 自主访谈 Agent

核心流程：
    评估(info sufficient?) → 提问 → 等待回答 → 记录 → 再评估 → 循环
    直到信息足够或达到最大轮数，进入生图阶段。

状态持久化：
    interview_state 保存到 session，页面刷新后可恢复。
"""
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str       # "agent" | "user"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ChatMessage":
        return cls(role=data["role"], content=data["content"], timestamp=data.get("timestamp", ""))


class InterviewAgent:
    """
    会话级自主访谈 Agent。
    
    每个会话同一时间只能有一个 InterviewAgent 在运行。
    通过 asyncio.Event 阻塞等待用户回答。
    """
    
    MAX_TURNS = 8
    MIN_TURNS = 2
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turn_count = 0
        self.conversation_history: List[ChatMessage] = []
        self.state = "idle"           # idle / evaluating / asking / waiting / complete
        self.answer_event = asyncio.Event()
        self.last_answer: Optional[str] = None
        self._manager = getattr(InterviewAgent, '_manager', None)  # 继承类级别注入的 manager
        self._orchestrator = None     # AgentOrchestrator，注入后用于提交 Plan
        
        # 本地 VLM 分析结果（文字摘要，由外部注入）
        self._analysis_result: Optional[Dict] = None
        
        # LLM 服务延迟初始化（避免循环导入）
        self._llm = None
    
    def _get_llm(self):
        """延迟初始化云端 LLM 服务（Kimi，仅处理文字）"""
        if self._llm is None:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from services.llm.core import create_cloud_llm_service
            self._llm = create_cloud_llm_service(self.session_id)
        return self._llm
    
    def set_manager(self, manager):
        """注入 WebSocket manager"""
        self._manager = manager
    
    def set_orchestrator(self, orchestrator):
        """注入 AgentOrchestrator"""
        self._orchestrator = orchestrator
    
    def set_analysis_result(self, result: Dict):
        """注入本地 VLM 分析结果（Qwen3.5 文字输出）"""
        self._analysis_result = result
    
    # ─────────────────────────────────────────────
    # 主循环
    # ─────────────────────────────────────────────
    
    async def run(self):
        """启动访谈主循环
        
        支持从持久化状态恢复：
        - waiting → 继续等待当前回答
        - asking  → 重新发送当前问题
        - idle/evaluating → 从头开始
        """
        print(f"[InterviewAgent] 启动: session={self.session_id[:8]}..., state={self.state}")
        
        try:
            # ── 从 waiting 状态恢复：继续等待回答 ──
            if self.state == "waiting":
                print(f"[InterviewAgent] 从 waiting 恢复，继续等待回答")
                answer = await self._wait_for_answer()
                if answer == "[SKIP_INTERVIEW]":
                    await self._enter_image_generation()
                    return
                self.conversation_history.append(ChatMessage(role="user", content=answer))
                self.turn_count += 1
                await self._persist_state()
                print(f"[InterviewAgent] 恢复后完成第 {self.turn_count} 轮对话")
                # 恢复后继续下一轮循环
            
            # ── 从 asking 状态恢复：重新发送问题 ──
            elif self.state == "asking":
                print(f"[InterviewAgent] 从 asking 恢复，重新发送问题")
                if self.conversation_history and self.conversation_history[-1].role == "agent":
                    question = self.conversation_history[-1].content
                    await self._send_question(question)
                    self.state = "waiting"
                    await self._persist_state()
                    answer = await self._wait_for_answer()
                    if answer == "[SKIP_INTERVIEW]":
                        await self._enter_image_generation()
                        return
                    self.conversation_history.append(ChatMessage(role="user", content=answer))
                    self.turn_count += 1
                    await self._persist_state()
                    print(f"[InterviewAgent] 恢复后完成第 {self.turn_count} 轮对话")
                else:
                    # 没有可恢复的问题，从头开始
                    self.state = "evaluating"
            
            # ── 从头开始 ──
            if self.state in ("idle", "evaluating"):
                self.state = "evaluating"
                await self._persist_state()
            
            # ── 主循环 ──
            while self.turn_count < self.MAX_TURNS:
                # ── 评估：信息是否足够？ ──
                if self.turn_count >= self.MIN_TURNS:
                    is_sufficient = await self._is_sufficient()
                    if is_sufficient:
                        print(f"[InterviewAgent] 信息足够，进入生图阶段 (turn={self.turn_count})")
                        await self._enter_image_generation()
                        return
                
                # ── 生成问题 ──
                self.state = "asking"
                question = await self._generate_next_question()
                self.conversation_history.append(ChatMessage(role="agent", content=question))
                await self._persist_state()
                await self._send_question(question)
                
                # ── 等待用户回答 ──
                self.state = "waiting"
                await self._persist_state()
                answer = await self._wait_for_answer()
                
                # 检查跳过信号
                if answer == "[SKIP_INTERVIEW]":
                    await self._enter_image_generation()
                    return
                
                # ── 记录回答 ──
                self.conversation_history.append(ChatMessage(role="user", content=answer))
                self.turn_count += 1
                await self._persist_state()
                print(f"[InterviewAgent] 完成第 {self.turn_count} 轮对话")
            
            # 达到最大轮数，强制进入生图
            print(f"[InterviewAgent] 达到最大轮数 {self.MAX_TURNS}，强制进入生图")
            await self._enter_image_generation()
            
        except asyncio.CancelledError:
            print(f"[InterviewAgent] 被取消: session={self.session_id[:8]}...")
            raise
        except Exception as e:
            print(f"[InterviewAgent] 异常: {e}")
            import traceback
            traceback.print_exc()
            # 异常时也尝试进入生图，避免会话卡住
            await self._enter_image_generation()
    
    # ─────────────────────────────────────────────
    # 公共接口：接收用户回答
    # ─────────────────────────────────────────────
    
    def receive_answer(self, answer: str):
        """外部调用：用户提交了回答"""
        self.last_answer = answer
        self.answer_event.set()
    
    def skip(self):
        """外部调用：用户要求跳过访谈，直接进入生图"""
        self.last_answer = "[SKIP_INTERVIEW]"
        self.answer_event.set()
    
    # ─────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────
    
    async def _wait_for_answer(self) -> str:
        """阻塞等待用户回答
        
        注意：如果 answer_event 已经被设置（receive_answer 在 wait 之前调用），
        直接返回而不清除，避免竞态条件导致的死锁。
        """
        if not self.answer_event.is_set():
            await self.answer_event.wait()
        # 读取后清除，为下一轮做准备
        self.answer_event.clear()
        return self.last_answer or ""
    
    async def _is_sufficient(self) -> bool:
        """
        LLM 评估：当前对话历史是否足以生成有意义的图像变体？
        
        判断维度：
        - 是否已了解用户绘画时的情绪状态？
        - 是否已了解用户对绘画元素的个人联想？
        - 是否已了解用户希望探索的方向？
        """
        try:
            llm = self._get_llm()
            
            # 获取绘画分析
            analysis_text = await self._get_analysis_text()
            
            # 格式化对话历史
            conversation_text = self._format_conversation()
            
            prompt = f"""你是一位艺术表达引导伙伴。请评估以下对话是否已收集足够信息，可以为用户的绘画生成 3 个有意义的图像变体。

【绘画分析摘要】
{analysis_text[:600]}

【已完成的访谈对话】
{conversation_text}

【判断标准】
1. 是否已了解用户绘画时的情绪状态？（如：焦虑、平静、兴奋、孤独）
2. 是否已了解用户对绘画中关键元素的个人联想？（如：雨=压力，伞=保护，人物=自我）
3. 是否已了解用户希望探索或改变的方向？（如：更温暖、更自由、更有力量）

如果以上 3 条中至少 2 条已有明确信息，回答 "sufficient"。
如果信息仍不足，回答 "insufficient" 并简要说明还缺什么。

请只输出 JSON，不要任何解释：
{{"sufficient": true/false, "reasoning": "简短理由"}}"""
            
            response = await asyncio.to_thread(llm.generate, prompt, force_json=True)
            result = json.loads(response)
            sufficient = result.get("sufficient", False)
            reasoning = result.get("reasoning", "")
            print(f"[InterviewAgent] 评估结果: sufficient={sufficient}, reasoning={reasoning}")
            return sufficient
            
        except Exception as e:
            print(f"[InterviewAgent] 评估失败，默认继续追问: {e}")
            return False
    
    async def _generate_next_question(self) -> str:
        """
        LLM 生成下一个问题。
        
        要求：
        - 简短（不超过 30 字）
        - 一次只问一个问题
        - 避免重复之前问过的问题
        - 聚焦用户尚未透露的情绪或联想
        """
        try:
            llm = self._get_llm()
            
            analysis_text = await self._get_analysis_text()
            conversation_text = self._format_conversation()
            
            # 提取已问过的问题，避免重复
            asked_questions = [msg.content for msg in self.conversation_history if msg.role == "agent"]
            asked_summary = "\n".join([f"- {q}" for q in asked_questions[-5:]])  # 最近 5 个问题
            
            prompt = f"""你是一位艺术表达引导伙伴。请根据绘画分析和已有对话，生成下一个最合适的开放式问题。

【绘画分析摘要】
{analysis_text[:400]}

【已完成的对话】
{conversation_text}

【已问过的问题（避免重复）】
{asked_summary}

【要求】
- 问题要简短（不超过 30 字）
- 一次只问一个问题
- 不要重复上面已问过的问题
- 聚焦用户尚未透露的情绪感受或个人联想
- 语气温和、探索性，不带诊断色彩

请只输出 JSON，不要任何解释：
{{"question": "...", "target": "这个问题想探查什么"}}"""
            
            response = await asyncio.to_thread(llm.generate, prompt, force_json=True)
            result = json.loads(response)
            question = result.get("question", "这幅画让你想到了什么？")
            target = result.get("target", "")
            print(f"[InterviewAgent] 生成问题: {question} (target: {target})")
            return question
            
        except Exception as e:
            print(f"[InterviewAgent] 生成问题失败，使用兜底: {e}")
            # 兜底问题列表
            fallback_questions = [
                "这幅画让你想到了什么？",
                "画中哪个元素最能代表你现在的感受？",
                "如果你能给这幅画加一个东西，你会加什么？",
                "画的时候，你的心情是怎样的？",
                "这幅画有没有让你想起某个时刻？",
            ]
            idx = min(self.turn_count, len(fallback_questions) - 1)
            return fallback_questions[idx]
    
    async def _enter_image_generation(self):
        """
        访谈完成，进入生图阶段。
        
        1. 发送 interview_complete 消息给前端
        2. 基于完整对话历史生成图像编辑指令
        3. 提交生图 Plan
        """
        self.state = "complete"
        await self._persist_state()
        
        # 通知前端
        await self._send_interview_complete()
        
        # 生成图像编辑指令
        try:
            variations = await self._generate_image_variations()
            
            # 提交生图 Plan
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from agent.plan import Plan, Step
            from agent.orchestrator import AgentOrchestrator
            
            if self._orchestrator is None:
                raise RuntimeError("Orchestrator 未注入，无法提交生图 Plan")
            
            plan = Plan(session_id=self.session_id, steps=[
                Step(tool_name="GenerateImageTool", input_context={
                    "variations": variations,
                    "conversation_summary": self._format_conversation()
                }),
            ])
            await self._orchestrator.submit_plan(self.session_id, plan)
            print(f"[InterviewAgent] 已提交生图 Plan")
            
        except Exception as e:
            print(f"[InterviewAgent] 进入生图阶段失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _generate_image_variations(self) -> List[Dict]:
        """基于对话历史生成 3 个图像编辑指令"""
        try:
            llm = self._get_llm()
            analysis_text = await self._get_analysis_text()
            conversation_text = self._format_conversation()
            
            prompt = f"""你是一位艺术表达引导伙伴。基于以下绘画分析和用户访谈对话，生成 3 个不同方向的图像编辑变体。

【绘画分析摘要】
{analysis_text[:400]}

【用户访谈对话】
{conversation_text}

【要求】
为用户的绘画生成 3 个不同情感方向的图像变体：
1. 温暖变体：朝积极、温暖、被接纳的方向转化
2. 冷色调变体：朝冷静、疏离、内省的方向转化
3. 高饱和变体：朝强烈情绪表达、释放的方向转化

每个变体包含：
- name: 变体名称
- description: 变体描述（心理意义）
- edit_prompt: 英文图像编辑指令（详细描述如何修改画面）
- color_prompt: 英文色彩描述
- hypothesis_id: 关联的猜想 ID

请只输出 JSON 数组，不要任何解释：
[
  {{"id": "warmth", "name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "...", "hypothesis_id": "hypo-warmth"}},
  ...
]"""
            
            response = await asyncio.to_thread(llm.generate, prompt, force_json=True)
            variations = json.loads(response)
            if not isinstance(variations, list):
                variations = variations.get("variations", [])
            print(f"[InterviewAgent] 生成 {len(variations)} 个图像变体指令")
            return variations[:3]
            
        except Exception as e:
            print(f"[InterviewAgent] 生成图像变体失败，使用默认: {e}")
            return self._default_variations()
    
    def _default_variations(self) -> List[Dict]:
        """默认图像变体（兜底）"""
        return [
            {
                "id": "warmth",
                "name": "温暖变体",
                "description": "朝积极、温暖的方向转化",
                "edit_prompt": "Add warm golden sunlight streaming through the scene, enhance warm colors, make the atmosphere comforting",
                "color_prompt": "warm amber, soft gold, peach tones",
                "hypothesis_id": "hypo-warmth"
            },
            {
                "id": "cool",
                "name": "冷色调变体",
                "description": "朝冷静、内省的方向转化",
                "edit_prompt": "Transform into cool blue tones, add misty atmosphere, create a sense of quiet introspection",
                "color_prompt": "cool blue, silver, pale cyan",
                "hypothesis_id": "hypo-cool"
            },
            {
                "id": "vibrant",
                "name": "高饱和变体",
                "description": "朝强烈情绪表达的方向转化",
                "edit_prompt": "Highly saturate all colors, make the image vivid and expressive, enhance emotional intensity",
                "color_prompt": "vibrant red, electric blue, bright yellow",
                "hypothesis_id": "hypo-vibrant"
            }
        ]
    
    # ─────────────────────────────────────────────
    # 状态持久化
    # ─────────────────────────────────────────────
    
    async def _persist_state(self):
        """将 Agent 状态持久化到数据库"""
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from models import Session
            
            session = Session.load(self.session_id)
            if session:
                session.interview_state = self.to_dict()
                session.conversation_history = [msg.to_dict() for msg in self.conversation_history]
                # 状态同步
                if self.state == "complete":
                    from models import SessionStatus
                    session.status = SessionStatus.GENERATING
                session.save()
        except Exception as e:
            print(f"[InterviewAgent] 状态持久化失败: {e}")
    
    def to_dict(self) -> Dict:
        return {
            "turn_count": self.turn_count,
            "state": self.state,
            "conversation": [msg.to_dict() for msg in self.conversation_history],
        }
    
    @classmethod
    def from_dict(cls, session_id: str, data: Dict) -> "InterviewAgent":
        """从持久化状态恢复 Agent"""
        agent = cls(session_id)
        agent.turn_count = data.get("turn_count", 0)
        agent.state = data.get("state", "idle")
        for msg_data in data.get("conversation", []):
            agent.conversation_history.append(ChatMessage.from_dict(msg_data))
        return agent
    
    # ─────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────
    
    async def _get_analysis_text(self) -> str:
        """获取绘画分析文本（优先使用注入的本地 VLM 结果）

        _analysis_result 和 session.initial_analysis 存储的都是
        parsers.standardize_analysis_result() 的输出格式：
        {analysis: {...}, questions: [...], hypotheses: [...]}
        """
        def _extract_analysis(obj: dict) -> str:
            """从 standardized 结果中提取 analysis 字段的 JSON 文本"""
            if not isinstance(obj, dict):
                return ""
            analysis = obj.get("analysis", {})
            if isinstance(analysis, dict) and analysis:
                return json.dumps(analysis, ensure_ascii=False)
            if isinstance(analysis, str) and analysis:
                return analysis
            return ""

        # 优先使用注入的分析结果
        if self._analysis_result is not None:
            if isinstance(self._analysis_result, dict):
                text = _extract_analysis(self._analysis_result)
                if text:
                    return text
            return str(self._analysis_result)

        # fallback: 从 session DB 读取
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from models import Session

            session = Session.load(self.session_id)
            if session and session.initial_analysis:
                if isinstance(session.initial_analysis, dict):
                    text = _extract_analysis(session.initial_analysis)
                    if text:
                        return text
                return str(session.initial_analysis)
        except Exception:
            pass
        return ""
    
    def _format_conversation(self) -> str:
        """格式化对话历史为文本"""
        lines = []
        for msg in self.conversation_history:
            role_label = "Agent" if msg.role == "agent" else "用户"
            lines.append(f"{role_label}: {msg.content}")
        return "\n".join(lines)
    
    async def _send_question(self, question: str):
        """通过 WebSocket 发送问题给受试者"""
        if self._manager is None:
            return
        try:
            await self._manager.send_to_subject(self.session_id, {
                "type": "chat_question",
                "data": {
                    "question": question,
                    "turn": self.turn_count + 1,
                    "max_turns": self.MAX_TURNS,
                    "state": self.state,
                }
            })
            print(f"[InterviewAgent] 已发送问题 (turn={self.turn_count + 1}): {question[:40]}...")
        except Exception as e:
            print(f"[InterviewAgent] 发送问题失败: {e}")
    
    async def _send_interview_complete(self):
        """通知前端访谈完成"""
        if self._manager is None:
            return
        try:
            await self._manager.send_to_subject(self.session_id, {
                "type": "interview_complete",
                "data": {
                    "total_turns": self.turn_count,
                    "state": self.state,
                }
            })
            print(f"[InterviewAgent] 已发送 interview_complete")
        except Exception as e:
            print(f"[InterviewAgent] 发送完成通知失败: {e}")
