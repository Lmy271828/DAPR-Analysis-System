"""
LLM Prompt 模块

分离为两个子模块：
- multimodal: 端侧 VLM（图像/视频分析）
- cloud: 云端 LLM（纯文字问答/报告）

保持向后兼容：从本模块导入的接口仍然可用。
"""
from services.llm.prompts.multimodal import build_image_analysis_prompt, build_video_analysis_prompt
from services.llm.prompts.cloud import (
    build_edit_instructions_prompt,
    build_follow_up_questions_prompt,
    build_final_report_prompt,
    build_repair_prompt,
)

__all__ = [
    "build_image_analysis_prompt",
    "build_video_analysis_prompt",
    "build_edit_instructions_prompt",
    "build_follow_up_questions_prompt",
    "build_final_report_prompt",
    "build_repair_prompt",
]
