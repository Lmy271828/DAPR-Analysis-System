"""
JSON Schema 定义 —— 用于 lm-format-enforcer 约束解码

这些 Schema 在 model.generate() 时作为 logits processor 传入，
强制模型输出 100% 合法的 JSON，消除 markdown 包裹、字段名错误、括号不匹配等问题。
"""

# ═══════════════════════════════════════════════════════════════
#  Schema 已冻结 —— 任何修改需经架构评审
# ═══════════════════════════════════════════════════════════════
# 冻结日期: 2026-05-17
# 冻结原因: 统一为嵌套格式（analysis 对象），彻底消除扁平化/嵌套双版本
# 变更历史:
#   - 2026-05-17: 移除扁平化兼容，analysis 内嵌 drawing_features/
#                 expression_observation/process_observation
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 图像分析 Schema（Batch A：绘画成品）
# ═══════════════════════════════════════════════════════════════

IMAGE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "drawing_features": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["drawing_features"]
}

# ═══════════════════════════════════════════════════════════════
# 视频分析 Schema（Batch B：webcam + canvas）
# ═══════════════════════════════════════════════════════════════

VIDEO_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "expression_observation": {
            "type": "array",
            "items": {"type": "string"}
        },
        "process_observation": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["expression_observation", "process_observation"]
}

# NOTE: 旧版 MULTIMODAL_ANALYSIS_SCHEMA 和 ANALYSIS_JSON_SCHEMA（含 status/data 包装层）
# 已于 2026-05-18 移除。当前使用 IMAGE_ANALYSIS_SCHEMA + VIDEO_ANALYSIS_SCHEMA 分 batch 约束解码。
