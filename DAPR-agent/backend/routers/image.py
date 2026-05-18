import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import SESSIONS_DIR, OUTPUTS_DIR
from models import Session, SessionStatus, TherapistLog
from schemas import SelectImageRequest, FinalAnswerRequest
from llm_service import create_llm_service
from image_service import get_image_service
from agent.plan import plan_after_selection, plan_after_final_answers
from dependencies import manager, orchestrator, log_to_therapist

router = APIRouter(prefix="/api/session")
file_router = APIRouter()


@file_router.get("/api/image/{session_id}/{filename}")
async def get_image(session_id: str, filename: str):
    """获取生成的图像"""
    image_path = OUTPUTS_DIR / session_id / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图像不存在")
    
    return FileResponse(image_path)


@router.post("/{session_id}/select")
async def select_image(session_id: str, request: SelectImageRequest):
    """用户选择图像"""
    # 验证路径参数和请求体中的 session_id 一致
    if session_id != request.session_id:
        raise HTTPException(status_code=400, detail="会话ID不匹配")
    
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session.selected_image_id = request.image_id
    session.selection_behavior = request.selection_behavior  # 保存选择行为数据
    session.status = SessionStatus.FINAL_ANALYSIS
    session.save(SESSIONS_DIR)
    
    # 记录选择行为日志
    if request.selection_behavior:
        log = TherapistLog(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            stage="image_selection",
            llm_input={},
            llm_output={},
            data={
                "selected_image_id": request.image_id,
                "selection_behavior": request.selection_behavior
            }
        )
        log_to_therapist(log)
        print(f"[Selection] 记录选择行为: session={session_id[:8]}..., 犹豫指标数={len(request.selection_behavior.get('hesitationIndicators', []))}")
    
    # 异步进行最终分析（Agent Plan 编排）
    plan = plan_after_selection(request.session_id)
    asyncio.create_task(orchestrator.submit_plan(request.session_id, plan))
    
    return {"status": "final_analysis_started"}


@router.post("/{session_id}/final-answers")
async def submit_final_answers(session_id: str, request: FinalAnswerRequest):
    """提交最终回答，生成完整报告"""
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 保存最终答案
    session.final_answers = request.answers
    session.save(SESSIONS_DIR)
    
    print(f"[Final Answers] 收到最终回答: {request.answers}")
    
    # 保存最终问答到对话历史
    llm = create_llm_service(request.session_id)
    final_qa_text = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in zip(session.final_questions, request.answers)])
    llm.conversation.add_message("user", f"【最终问题回答】\n{final_qa_text}")
    
    # 保存选择行为到对话历史
    if session.selection_behavior:
        sel = session.selection_behavior
        behavior_text = f"【图像选择行为】\n查看顺序: {sel.get('viewOrder', [])}\n"
        behavior_text += f"最终选择: 第{sel.get('finalSelection', {}).get('viewOrder', 'N/A')}个查看的图像\n"
        behavior_text += f"犹豫指标: {len(sel.get('hesitationIndicators', []))}个"
        llm.conversation.add_message("system", behavior_text)
    
    # 异步生成最终报告（Agent Plan 编排）
    plan = plan_after_final_answers(request.session_id)
    asyncio.create_task(orchestrator.submit_plan(request.session_id, plan))
    
    return {"status": "final_report_generating"}


async def generate_images_task(session_id: str, variations=None, conversation_summary=None):
    """后台生成图像任务
    
    Args:
        variations: 如果提供（来自 InterviewAgent），直接使用；否则由 LLM 生成
        conversation_summary: 访谈对话摘要（可选，用于日志记录）
    """
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    # 敏感数据不上云端：图像生成任务不调用云端 LLM 处理图像
    # variations 应由 InterviewAgent（或本地 VLM 分析阶段）预生成
    if variations is None:
        print(f"[GenerateImageTool] 警告: InterviewAgent 未提供变体，使用默认兜底")
        variations = [
            {"id": "warmth", "name": "温暖变体", "description": "朝积极、温暖的方向转化",
             "edit_prompt": "Add warm golden sunlight streaming through the scene, enhance warm colors, make the atmosphere comforting",
             "color_prompt": "warm amber, soft gold, peach tones", "hypothesis_id": "hypo-warmth"},
            {"id": "cool", "name": "冷色调变体", "description": "朝冷静、内省的方向转化",
             "edit_prompt": "Transform into cool blue tones, add misty atmosphere, create a sense of quiet introspection",
             "color_prompt": "cool blue, silver, pale cyan", "hypothesis_id": "hypo-cool"},
            {"id": "vibrant", "name": "高饱和变体", "description": "朝强烈情绪表达的方向转化",
             "edit_prompt": "Highly saturate all colors, make the image vivid and expressive, enhance emotional intensity",
             "color_prompt": "vibrant red, electric blue, bright yellow", "hypothesis_id": "hypo-vibrant"}
        ]
    else:
        print(f"[GenerateImageTool] 使用 InterviewAgent 提供的 {len(variations)} 个变体")
    
    image_service = get_image_service()
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="generate_instructions",
        llm_input={
            "hypotheses": session.hypotheses,
            "drawing": session.drawing_image
        },
        llm_output={"variations": variations}
    )
    log_to_therapist(log)
    
    # 生成图像（异步批量提交 + 并行轮询 + 自动预热）
    output_dir = OUTPUTS_DIR / session_id
    generated = await image_service.generate_variations_async(
        input_image_path=session.drawing_image,
        variations=variations,
        output_dir=str(output_dir),
        do_warmup=True,
    )
    
    session.generated_images = generated
    session.status = SessionStatus.SELECTING
    session.save(SESSIONS_DIR)
    
    # 发送给受试者
    await manager.send_to_subject(session_id, {
        "type": "generated_images",
        "data": {
            "images": [
                {
                    "id": img["id"],
                    "name": img["name"],
                    "description": img["description"],
                    "url": f"/api/image/{session_id}/{img['filename']}"
                }
                for img in generated
            ]
        }
    })
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="image_generation",
        llm_input={"variations": variations},
        llm_output={"status": "success", "count": len(generated)},
        flux2_input={"workflow": "color_the_dapr_doodle"},
        flux2_output={"generated_images": generated}
    )
    log_to_therapist(log)


async def final_analysis_task(session_id: str):
    """后台最终分析问题生成任务（第5步第1阶段）"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    print(f"[Final Analysis] 开始生成最终问题: {session_id}")
    # 使用云端 LLM（Kimi）处理纯文字问答，不接触原始图像
    from services.llm.core import create_cloud_llm_service
    llm = create_cloud_llm_service(session_id)
    
    # 找到选中的图像
    selected_image = _find_selected_image(session)
    print(f"[Final Analysis] 用户选择图像: {selected_image.get('name', 'unknown')}")
    
    # 根据选择、选择行为数据和访谈对话历史生成深入问题（纯文字，无图像上传）
    follow_up_questions = llm.generate_follow_up_questions(
        selected_image=selected_image,
        hypotheses=session.hypotheses,
        conversation_history=session.conversation_history,
        selection_behavior=session.selection_behavior
    )
    
    # 保存待问的问题
    session.final_questions = follow_up_questions
    session.status = SessionStatus.FINAL_QUESTIONS  # 新状态：等待回答最终问题
    session.save(SESSIONS_DIR)
    
    # 发送问题给用户
    await manager.send_to_subject(session_id, {
        "type": "final_questions",
        "data": {
            "questions": follow_up_questions,
            "selected_image": {
                "name": selected_image.get("name"),
                "description": selected_image.get("description")
            }
        }
    })
    
    print(f"[Final Analysis] 已发送最终问题: {follow_up_questions}")
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="final_questions_generated",
        llm_input={
            "selected_image": selected_image,
            "hypotheses": session.hypotheses
        },
        llm_output={"questions": follow_up_questions}
    )
    log_to_therapist(log)


async def generate_final_report_task(session_id: str):
    """生成最终报告任务（第5步第2阶段）"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    print(f"[Final Report] 开始生成最终报告: {session_id}")
    # 使用云端 LLM（Kimi）生成最终报告（纯文字，无图像上传）
    from services.llm.core import create_cloud_llm_service
    llm = create_cloud_llm_service(session_id)
    
    # 找到选中的图像
    selected_image = _find_selected_image(session)
    
    # 从 conversation manager 获取完整的对话历史（包含分析结果）
    conversation_history = llm.conversation.get_messages(include_summary=True)
    print(f"[Final Report] 对话历史: {len(conversation_history)} 条消息")
    
    # 构建用户信息
    user_info = {
        "age_group": session.age_group,
        "gender": session.gender
    }
    
    # 生成最终分析报告（传入更多上下文）
    final_result = llm.generate_final_report(
        selected_image=selected_image,
        previous_hypotheses=session.hypotheses,
        conversation_history=conversation_history,
        final_answers=session.final_answers,
        drawing_analysis=session.initial_analysis,
        selection_behavior=session.selection_behavior,
        user_info=user_info
    )
    
    session.final_analysis = final_result
    session.status = SessionStatus.COMPLETED
    session.save(SESSIONS_DIR)
    
    # 发送最终报告给用户
    await manager.send_to_subject(session_id, {
        "type": "final_report",
        "data": final_result
    })
    
    print(f"[Final Report] 最终报告已生成")
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="final_report",
        llm_input={
            "selected_image": selected_image,
            "hypotheses": session.hypotheses,
            "final_answers": session.final_answers
        },
        llm_output=final_result
    )
    log_to_therapist(log)
