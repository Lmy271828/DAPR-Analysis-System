"""
云端 LLM Prompt 模块（纯文字任务专用）

负责后续问题生成、最终报告、图像变体指令等纯文字任务，不涉及图像/视频分析。
"""
import json
from typing import Dict, List


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


def build_follow_up_questions_prompt(selected_image: Dict, conversation_text: str, hypotheses: List[Dict], selection_text: str = "") -> str:
    """构建后续问题生成 prompt"""
    return f"""【绘画探索深度访谈 - 图像选择】

用户选择了图像变体：{selected_image.get('name', '未知')}
变体描述：{selected_image.get('description', '无描述')}

【选择行为观察 - 实际数据】
{selection_text if selection_text else "（无选择行为数据）"}

【选择行为的心理解读参考】
- 查看多张图后决定：内心可能存在多种可能性的权衡
- 对某图长时间注视但未选择：对该氛围有深层认同但存在防御（"渴望但不敢要"）
- 最终选择非首张查看：直觉偏好与理性判断分离
- 毫不犹豫首选即决：该变体与当前自我状态高度一致
- 请基于上述实际数据，生成针对用户真实选择过程的深入问题

【访谈对话历史】
{conversation_text}

【探索方向】
{json.dumps(hypotheses, ensure_ascii=False, indent=2)}

【深度询问原则】
1. **认同探索**：用户选择的图像往往代表其某种认同或好奇
2. **对比观察**：对比原始绘画与选择变体的差异，发现有趣的视角
3. **自我概念对话**：通过选择行为开启关于自我形象的温和对话
4. **过程追问**：关注"为什么选择这张而非那张"的决策过程，这比结果更能反映内在状态
5. **犹豫即线索**：如果用户有犹豫行为，温和地探索犹豫背后的张力

【问题生成要求】
生成1-2个开放式深入问题，要求：
1. **必须基于实际选择行为数据**：如果用户查看了多张图，追问对比过程；如果用户犹豫过，追问犹豫瞬间的感受
2. 关联原始绘画分析中发现的画面特点，但不在问题中直接提及具体的对应关系
3. 温和、非评判，鼓励自我探索
4. 有助于发现用户真实的感受和想法

【示例问题类型】
- "您对'温暖庇护'和'宁静平衡'都看了很长时间，最终选择了'宁静平衡'——那个让您犹豫的瞬间，心里闪过了什么？"
- "您第一张看的是'雨中希望'，但最后选了'温暖庇护'——是什么让直觉和最终决定走向了不同方向？"
- "您几乎没有犹豫就选了这张——这个画面一下子打动了您的，是什么？"
- "您反复对比了几张图，能说说每个画面带给您的不同感觉吗？"

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
