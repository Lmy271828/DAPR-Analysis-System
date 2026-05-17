"""
LLM Prompt 构建函数

本模块负责根据用户画像、素材类型和会话状态，动态组装提示文本。
采用"分层提示组装"架构：
  Layer 1: 核心系统提示（static，所有 session 共享）
  Layer 2: 知识片段（根据 user_profile 动态选择注入）
  Layer 3: 任务指令 + 素材描述（运行时动态生成）
"""
import json
from typing import Dict, List, Optional

from services.llm.knowledge import get_knowledge_fragments, get_analysis_knowledge, get_interview_knowledge


# ───────────────────────────────────────────────
# 知识片段选择（从 dapr_knowledge_base/ 文件加载）
# ───────────────────────────────────────────────

def select_knowledge_fragments(
    user_profile: Optional[Dict] = None
) -> str:
    """根据用户画像选择相关知识片段注入提示。

    当前从 dapr_knowledge_base/ 文件动态加载，保留原有接口。
    未来若支持多语言/多文化/多年龄段，可升级为 sqlite-vec 轻量检索。
    """
    return get_analysis_knowledge(user_profile=user_profile)


# ───────────────────────────────────────────────
# Prompt 构建函数
# ───────────────────────────────────────────────

def build_analysis_prompt(
    has_webcam: bool,
    has_screen: bool,
    video_info_section: str,
    user_profile: Optional[Dict] = None,
) -> str:
    """构建绘画分析 prompt。

    Args:
        has_webcam: 是否有 webcam 视频
        has_screen: 是否有 canvas 录制视频
        video_info_section: 视频元信息描述文本
        user_profile: 用户画像，可选字段：age(int), culture(str)
    """
    knowledge_fragments = select_knowledge_fragments(user_profile)

    return f"""请分析提供的素材（视频帧按时序排列）
1. 第一张图像：绘画成品
{"2. 第一个视频：绘画时的面部表情变化" if has_webcam else ""}
{("3. 第二个视频：绘画过程" if has_webcam else "2. 第一个视频：绘画过程") if has_screen else ""}
{video_info_section}

{knowledge_fragments}

JSON结构必须包含以下字段：
{{
  "analysis": {{...详细分析...}},
  "questions_for_user": ["问题1", "问题2", "问题3"],
  "psychological_guesstimates": ["猜想1", "猜想2", "猜想3"]
}}

对受试者的提问应简洁明了

【严格输出契约（必须遵守）】
仅返回 JSON，不要 markdown，不要解释文字，不要多余前后缀。
输出必须为以下顶层结构之一：
1) 成功：
{{
  "status": "ok",
  "data": {{
    "analysis": {{...}},
    "questions_for_user": ["..."],
    "psychological_guesstimates": ["..."]
  }}
}}
2) 无法确定/失败：
{{
  "status": "unknown",
  "error": {{
    "code": "INSUFFICIENT_INFO",
    "message": "原因"
  }}
}}
禁止输出任何其他顶层字段。"""


def build_edit_instructions_prompt(analysis_summary: str, hypotheses: List[Dict]) -> str:
    """构建图像编辑指令 prompt"""
    return f"""【任务】基于绘画分析，生成3个图像创意变体（保持与原图高度一致）

【分析基础】
"雨中人"绘画是一种表达性艺术媒介，画面元素可以反映创作者对自我、环境与资源的想象：
- 雨象征外部氛围或挑战
- 防护装备象征创作者想象出的保护方式
- 人物表征反映创作者对自我形象的想象

【当前画面分析】
{analysis_summary}

【探索方向】
{json.dumps(hypotheses, ensure_ascii=False, indent=2)}

【创意变体原则】
三个变体应分别代表不同的情感氛围或视角方向，方向应参考【当前画面分析】和【探索方向】

【输出格式】
{{
  "status": "ok",
  "data": [
    {{"name": "中文名称（体现氛围方向）", "description": "中文描述（氛围说明）", "edit_prompt": "英文图像编辑指令（轻量、保结构）", "color_prompt": "英文色彩描述（轻量色调调整）"}},
    {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}},
    {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}}
  ]
}}

【严格要求】
1. 必须按照【输出格式】生成恰好3个变体，每个变体必须包含全部4个字段
2. edit_prompt和color_prompt使用英文，简洁明了，每条不超过30个单词
3. name和description使用中文，温和、有画面感，避免病理化术语
4. 只输出JSON，不要markdown代码块，不要解释文字，不要多余字段

"""


def build_follow_up_questions_prompt(selected_image: Dict, conversation_text: str, hypotheses: List[Dict]) -> str:
    """构建后续问题生成 prompt"""
    return f"""【绘画探索深度访谈 - 图像选择】

用户选择了图像变体：{selected_image.get('name', '未知')}
变体描述：{selected_image.get('description', '无描述')}

【选择行为观察】
用户选择该变体可能反映：
- 对该变体所代表氛围的认同或向往
- 对当前自我状态的某种表达
- 对另一种可能性的好奇

【访谈对话历史】
{conversation_text}

【探索方向】
{json.dumps(hypotheses, ensure_ascii=False, indent=2)}

【深度询问原则】
1. **认同探索**：用户选择的图像往往代表其某种认同或好奇
2. **对比观察**：对比原始绘画与选择变体的差异，发现有趣的视角
3. **自我概念对话**：通过选择行为开启关于自我形象的温和对话
4. **开放性评估**：评估用户对不同氛围的接受程度

【问题生成要求】
生成1-2个开放式深入问题，要求：
1. 基于绘画探索的理念，温和地探讨选择背后的感受
2. 关联原始绘画分析中发现的画面特点，但不在问题中直接提及具体的对应关系
3. 温和、非评判，鼓励自我探索
4. 有助于发现用户真实的感受和想法

【示例问题类型】
- "这张图片中的[元素]与您最初的画作有什么不同？这种变化对您意味着什么？"
- "如果画中的人物是您自己，选择这个版本让您有什么样的感受？"
- "在这个场景中，您感受到的[氛围]来自哪里？"

【输出格式】
只返回JSON数组格式的问题列表，不要任何解释：
["问题1...", "问题2..."]"""


def build_final_report_prompt(
    user_info_text: str,
    scoring_data: str,
    selected_image: Dict,
    selection_text: str,
    conversation_text: str,
    previous_hypotheses: List[Dict],
    final_answers: List[str]
) -> str:
    """构建最终报告 prompt"""
    dialog_section = ""
    if previous_hypotheses and final_answers:
        dialog_section = "\n".join([
            f"探索{i+1}: {h.get('description', str(h)) if isinstance(h, dict) else str(h)}\n用户的分享: {a}"
            for i, (h, a) in enumerate(zip(previous_hypotheses, final_answers))
        ])
    else:
        dialog_section = "（暂无详细对话）"

    return f"""【一次"雨中人"绘画旅程的回顾】

你是一位温暖的艺术表达伙伴。用户刚刚完成了一次"雨中人"绘画探索——这不是测试，也不是诊断，而是一次通过画画、选图和对话来了解自己的创意旅程。
请基于以下旅程中的素材，为用户写一份真诚、温暖的回顾。

## 一、旅程素材

### 1.1 用户基本信息
{user_info_text if user_info_text else "（未提供）"}

### 1.2 绘画观察笔记
{scoring_data if scoring_data else "（无绘画分析数据）"}

### 1.3 用户选择的画面
- 画面名称: {selected_image.get('name', '未知名称')}
- 画面描述: {selected_image.get('description', '无描述')}

{selection_text if selection_text else ""}

### 1.4 对话中的闪光时刻
{dialog_section}

{conversation_text if conversation_text else ""}

## 二、输出要求

请只输出一段合法的 JSON，且 JSON 中只能包含以下三个**扁平字段**，禁止出现任何嵌套对象：

- `summary`：string，用 2-4 句话像朋友一样分享你对这次创作旅程的整体感受。温暖、真诚、有画面感。不要使用"患者""症状""风险""干预""诊断""低/中/高/危机"等词汇。
- `creative_insights`：string[]，3-5 条。从绘画特征、画面选择或对话回答中看到的有趣视角、诗意联想或内心状态的隐喻。用"我注意到……""这幅画让我想到……"这样的主观分享语气。每条 1-2 句话。
- `suggested_explorations`：string[]，2-4 条。轻松、无压力的后续探索建议。可以是艺术小练习、日常观察角度，或一个开放的思考方向。避免命令式语气，不说"你应该"，多说"如果你想继续玩……""也许可以试试看……"。

## 三、语气与禁忌
- 你是用户的艺术表达伙伴，不是专家，更不是医生。
- 绝对禁止：临床术语、风险评级、分级体系（低/中/高/危机）、诊断结论、干预指令。
- 如果在素材中感受到用户的困扰，请用陪伴的语气回应（例如"这听起来不容易""愿意多说一点吗"），而不是给出指令式结论。
- 确保 JSON 格式正确，可被 `json.loads` 直接解析。

请只输出 JSON，不要输出 markdown 代码块标记（```json）或其他任何内容："""


def build_repair_prompt(current_text: str, last_error: str) -> str:
    """构建 JSON 修复 prompt"""
    return f"""你是JSON修复器。请把下列文本修复为合法JSON。
要求：
1. 只输出JSON，不要解释。
2. 顶层结构必须为：
{{"status":"ok","data":[{{"name":"","description":"","edit_prompt":"","color_prompt":""}},{{...}},{{...}}]}}
3. data 必须恰好3项，每项包含 name/description/edit_prompt/color_prompt 四个字段。

错误信息：{last_error}
原文本：
{current_text}
"""
