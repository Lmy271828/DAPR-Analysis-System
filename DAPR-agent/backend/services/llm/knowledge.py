"""
DAPR 知识库加载器 —— 从 dapr_knowledge_base/ 文件动态加载

本模块将知识库文档映射为 LLM prompt 可用的文本片段，
支持按主题(topic)和用户画像(user_profile)动态筛选注入。

知识库文件 -> topic 映射:
  01_theoretical_framework.md     -> theoretical_framework
  02_scoring_systems.md           -> scoring_systems
  03_cultural_adaptation.md       -> cultural_adaptation
  04_age_guidelines.md            -> age_guidelines
  05_ethical_guardrails.md        -> ethical_guardrails
  06_formal_elements.md           -> formal_elements
  07_ai_assessment_frontier.md    -> ai_assessment_frontier
"""
import os
from pathlib import Path
from typing import Dict, List, Optional


# topic -> 文件名映射
_TOPIC_FILES: Dict[str, str] = {
    "theoretical_framework": "01_theoretical_framework.md",
    "scoring_systems": "02_scoring_systems.md",
    "cultural_adaptation": "03_cultural_adaptation.md",
    "age_guidelines": "04_age_guidelines.md",
    "ethical_guardrails": "05_ethical_guardrails.md",
    "formal_elements": "06_formal_elements.md",
    "ai_assessment_frontier": "07_ai_assessment_frontier.md",
}

# 缓存：避免每次重复读文件
_KNOWLEDGE_CACHE: Dict[str, str] = {}


def _knowledge_base_dir() -> Path:
    """定位 dapr_knowledge_base/ 目录"""
    # 从本文件出发: backend/services/llm/knowledge.py
    # 目标: docs/dapr_knowledge_base/
    base = Path(__file__).parent.parent.parent.parent / "docs" / "dapr_knowledge_base"
    if base.exists():
        return base
    # fallback: 允许通过环境变量指定
    env_path = os.environ.get("DAPR_KNOWLEDGE_BASE")
    if env_path:
        return Path(env_path)
    raise FileNotFoundError("dapr_knowledge_base/ 目录未找到")


def _load_topic(topic: str) -> str:
    """加载单个 topic 的文档内容（带缓存）"""
    if topic in _KNOWLEDGE_CACHE:
        return _KNOWLEDGE_CACHE[topic]

    filename = _TOPIC_FILES.get(topic)
    if not filename:
        return ""

    filepath = _knowledge_base_dir() / filename
    if not filepath.exists():
        return ""

    content = filepath.read_text(encoding="utf-8")
    _KNOWLEDGE_CACHE[topic] = content
    return content


def get_knowledge_fragments(
    topics: Optional[List[str]] = None,
    user_profile: Optional[Dict] = None,
) -> str:
    """根据主题和用户画像获取知识库文本片段。

    Args:
        topics: 要加载的知识主题列表。
                默认 None 表示加载全部可用主题。
                访谈阶段推荐: ["ethical_guardrails", "theoretical_framework",
                               "formal_elements", "age_guidelines", "cultural_adaptation"]
        user_profile: 用户画像，可选字段:
            - age(int): 用于在 age_guidelines 前添加年龄聚焦提示
            - culture(str): 用于在 cultural_adaptation 前添加文化聚焦提示
            - gender(str): 保留字段，当前未影响知识筛选

    Returns:
        拼接后的知识文本，可直接注入 LLM prompt。
    """
    if topics is None:
        topics = list(_TOPIC_FILES.keys())

    fragments: List[str] = []

    for topic in topics:
        content = _load_topic(topic)
        if not content:
            continue

        # 根据 user_profile 在特定 topic 前添加聚焦提示
        header = f"【{topic.replace('_', ' ').title()}】"
        if topic == "age_guidelines" and user_profile:
            age = user_profile.get("age")
            if age is not None:
                header += f"\n> 用户年龄: {age} 岁。请重点关注与该年龄段相关的指导原则。"
        elif topic == "cultural_adaptation" and user_profile:
            culture = user_profile.get("culture")
            if culture:
                header += f"\n> 用户文化背景: {culture}。请重点关注与该文化相关的解释校准。"
            else:
                header += "\n> 用户文化背景未明确，默认按中国文化语境处理。"

        fragments.append(f"{header}\n\n{content}")

    return "\n\n---\n\n".join(fragments)


def get_interview_knowledge(user_profile: Optional[Dict] = None) -> str:
    """获取 InterviewAgent 访谈阶段推荐注入的知识片段。

    包含:
      - ethical_guardrails: 伦理约束（始终注入）
      - theoretical_framework: 理论框架（帮助访谈理解隐喻）
      - formal_elements: 形式元素观察（帮助关联绘画内容提问）
      - age_guidelines: 年龄指导（若已知年龄则聚焦）
      - cultural_adaptation: 文化适应（若已知文化则聚焦）
    """
    topics = [
        "ethical_guardrails",
        "theoretical_framework",
        "formal_elements",
        "age_guidelines",
        "cultural_adaptation",
    ]
    return get_knowledge_fragments(topics=topics, user_profile=user_profile)


def get_analysis_knowledge(user_profile: Optional[Dict] = None) -> str:
    """获取绘画分析阶段推荐注入的知识片段（兼容旧版 select_knowledge_fragments 的完整版）。"""
    topics = [
        "ethical_guardrails",
        "theoretical_framework",
        "scoring_systems",
        "formal_elements",
        "age_guidelines",
        "cultural_adaptation",
        "ai_assessment_frontier",
    ]
    return get_knowledge_fragments(topics=topics, user_profile=user_profile)
