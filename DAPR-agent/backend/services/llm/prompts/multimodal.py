"""
端侧 VLM Prompt 模块（多模态分析专用）

只负责图像/视频分析相关的 prompt 构建，不涉及云端纯文字任务。
"""
import os
from pathlib import Path
from typing import Dict, Optional

from services.llm.knowledge import get_analysis_knowledge


def _load_system_prompt() -> str:
    """加载端侧 VLM 系统提示词"""
    prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "DAPR_ANALYSIS_PROMPT.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""


def select_knowledge_fragments(user_profile: Optional[Dict] = None) -> str:
    """根据用户画像选择相关知识片段注入提示。"""
    return get_analysis_knowledge(user_profile=user_profile)


def build_analysis_prompt(
    has_webcam: bool,
    has_screen: bool,
    video_info_section: str,
    user_profile: Optional[Dict] = None,
) -> str:
    """构建绘画分析 prompt（端侧 VLM 专用）。

    Args:
        has_webcam: 是否有 webcam 视频
        has_screen: 是否有 canvas 录制视频
        video_info_section: 视频元信息描述文本
        user_profile: 用户画像，可选字段：age(int), culture(str)
    """
    system_prompt = _load_system_prompt()
    knowledge_fragments = select_knowledge_fragments(user_profile)

    material_section = "请分析提供的素材（视频帧按时序排列）：\n"
    material_section += "1. 第一张图像：绘画成品\n"
    if has_webcam:
        material_section += "2. 第一个视频：绘画时的面部表情变化\n"
    if has_screen:
        idx = 3 if has_webcam else 2
        material_section += f"{idx}. 第{'二' if has_webcam else '一'}个视频：绘画过程\n"

    return f"""{system_prompt}

{material_section}
{video_info_section}

{knowledge_fragments}

【严格输出契约（必须遵守）】
仅返回 JSON，不要 markdown，不要解释文字，不要多余前后缀。
输出必须为以下结构：
{{
  "drawing_features": ["画面中画有...，具体表现为...，位于...", "..."],
  "expression_observation": ["开始绘画时...，眉毛...，嘴角...", "..."],
  "process_observation": ["先画...，笔触...", "..."]
}}
三个字段必须是字符串数组，每个元素是一条独立的、尽可能详细的观察描述。
禁止输出任何其他顶层字段。"""
