"""
端侧 VLM Prompt 模块（多模态分析专用）

采用方案 B：
- Batch A（图像）：绘画成品 → drawing_features
- Batch B（视频）：webcam + canvas → expression_observation + process_observation

两批独立推理，结果合并后返回。
"""
import os
from pathlib import Path
from typing import Dict, Optional

from services.llm.knowledge import get_analysis_knowledge


def _load_system_prompt() -> str:
    """加载端侧 VLM 核心约束提示词"""
    prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "DAPR_ANALYSIS_PROMPT.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""


def select_knowledge_fragments(user_profile: Optional[Dict] = None) -> str:
    """根据用户画像选择相关知识片段注入提示。"""
    return get_analysis_knowledge(user_profile=user_profile)


def build_image_analysis_prompt(user_profile: Optional[Dict] = None) -> str:
    """构建图像分析 prompt（Batch A：绘画成品）。

    只分析静态画面元素，不涉及时序信息。
    """
    system_prompt = _load_system_prompt()
    knowledge_fragments = select_knowledge_fragments(user_profile)

    return f"""{system_prompt}

{knowledge_fragments}

【分析任务】
请详细分析这张绘画成品。你的任务是识别和描述画面中所有可见的艺术元素，包括但不限于：
- 雨量表现：密度、方向、动态感、在画面中的具体位置
- 天空与云层：晴朗/多云/阴沉/有光透出，厚度、形状、颜色、位置
- 闪电与风：有无、形态、动态线条
- 地面与积水：处理方式、水洼、倒影、材质
- 人物：完整性、细节丰富度、具体姿态、大小比例、位置、面部表情细节
- 防护与伴随：伞、雨衣、帽子、屋檐、树木、建筑、其他人/宠物
- 积极元素：彩虹、阳光、植物等

【输出格式】
只返回 JSON，不要 markdown，不要解释文字：
{{
  "drawing_features": [
    "画面中...，具体表现为...，位于...",
    "..."
  ]
}}
每个元素必须是一条独立的、尽可能详细的观察描述。
禁止输出任何其他顶层字段。"""


def build_video_analysis_prompt(
    has_webcam: bool,
    has_screen: bool,
    video_info_section: str,
    user_profile: Optional[Dict] = None,
) -> str:
    """构建视频分析 prompt（Batch B：webcam + canvas）。

    分析动态时序信息：表情变化和绘画过程。
    要求按时间维度细粒度描述，方便下游 LLM 推测时序因果逻辑。
    """
    system_prompt = _load_system_prompt()
    knowledge_fragments = select_knowledge_fragments(user_profile)

    material_section = "请分析以下视频帧（按时序排列）：\n"
    if has_webcam:
        material_section += "1. 第一个视频：绘画时的面部表情变化\n"
    if has_screen:
        idx = 2 if has_webcam else 1
        material_section += f"{idx}. 第{'二' if has_webcam else '一'}个视频：绘画过程\n"

    return f"""{system_prompt}

{knowledge_fragments}

{material_section}
{video_info_section}

【分析任务】
请按时间顺序详细分析上述视频帧。你的任务是描述动态变化过程，而非静态快照。

### 表情观察（expression_observation）
按时间顺序（开始→中间→结尾）描述面部表情变化，每条观察标注大致阶段：
- 眉毛状态：舒展、微皱、紧锁、挑眉
- 嘴角状态：上扬、下垂、平直、抿嘴
- 眼神状态：专注、游离、明亮、黯淡
- 整体情绪流动：从什么状态到什么状态，转折点在哪里

要求：每条描述尽量标注时间阶段（如"绘画初期""第3帧左右""收尾阶段"），方便下游对齐绘画动作。

### 过程观察（process_observation）
按时间顺序描述绘画过程的细节：
- 绘画顺序：具体先画什么、后画什么，每个阶段用了多久
- 笔触特点：线条轻重、速度快慢、流畅或犹豫
- 修改痕迹：哪些部分反复修改、擦除重画
- 停顿节点：在哪些位置有明显停顿或思考

要求：每条描述尽量标注时间阶段或与表情变化的对应关系（如"在表情放松的同时，开始画..."），方便下游推测"表情变化→绘画动作"的因果逻辑。

【输出格式】
只返回 JSON，不要 markdown，不要解释文字：
{{
  "expression_observation": [
    "绘画初期：眉毛舒展，嘴角微微上扬，眼神专注于...",
    "中期：...",
    "收尾阶段：..."
  ],
  "process_observation": [
    "开始时先画...，笔触...",
    "随后...",
    "结尾阶段..."
  ]
}}
每个元素必须是一条独立的、带时间维度的、尽可能详细的观察描述。
禁止输出任何其他顶层字段。"""
