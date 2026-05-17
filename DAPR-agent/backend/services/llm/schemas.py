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
# 多模态分析 Schema（本地 VLM 专用）
# 仅包含 analysis 对象，不包含 questions/hypotheses
# ═══════════════════════════════════════════════════════════════

MULTIMODAL_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "drawing_features": {
            "type": "array",
            "items": {"type": "string"}
        },
        "expression_observation": {
            "type": "array",
            "items": {"type": "string"}
        },
        "process_observation": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": [
        "drawing_features",
        "expression_observation",
        "process_observation"
    ]
}

# ═══════════════════════════════════════════════════════════════
# 完整分析 Schema（保留，用于需要 questions/hypotheses 的场景）
# ═══════════════════════════════════════════════════════════════

ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "unknown"]},
        "data": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "object",
                    "properties": {
                        "drawing_features": {"type": "object"},
                        "expression_observation": {"type": "object"},
                        "process_observation": {"type": "object"}
                    },
                    "required": [
                        "drawing_features",
                        "expression_observation",
                        "process_observation"
                    ]
                },
                "questions_for_user": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5
                },
                "psychological_guesstimates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5
                }
            },
            "required": [
                "analysis",
                "questions_for_user",
                "psychological_guesstimates"
            ]
        },
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"}
            },
            "required": ["code", "message"]
        }
    },
    "required": ["status"]
}
