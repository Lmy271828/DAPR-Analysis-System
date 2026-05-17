"""
JSON 解析、验证与标准化工具函数
"""
import json
import re
from typing import Dict, List, Optional, Tuple, Any


def clean_json_text(response: str) -> str:
    """清理模型响应中的包裹内容，尽量保留JSON主体"""
    cleaned = response or ""
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', cleaned)
    cleaned = cleaned.strip()
    # 截取首个 { 到最后一个 }，避免前后解释文本干扰
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return cleaned.strip()


# ═══════════════════════════════════════════════════════════════
# 图像分析契约（Batch A：绘画成品）
# ═══════════════════════════════════════════════════════════════

def validate_image_analysis_contract(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """校验图像分析输出契约"""
    if not isinstance(payload, dict):
        return False, "payload不是对象"
    if "drawing_features" not in payload:
        return False, "缺少字段: drawing_features"
    if not isinstance(payload["drawing_features"], list):
        return False, "drawing_features必须是数组"
    if not all(isinstance(x, str) for x in payload["drawing_features"]):
        return False, "drawing_features必须是字符串数组"
    return True, ""


def normalize_image_analysis_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将图像分析结果转换为内部兼容格式"""
    if not isinstance(payload, dict):
        return {"raw_response": str(payload)}
    return {
        "analysis": {"drawing_features": payload.get("drawing_features", [])},
        "questions_for_user": [],
        "psychological_guesstimates": []
    }


def parse_image_analysis_response(response: str) -> Dict[str, Any]:
    """解析图像分析响应（Batch A）"""
    current_text = response or ""
    cleaned = clean_json_text(current_text)
    print(f"[LLM-Image] 清理后响应 ({len(cleaned)} 字符):")
    print(cleaned[:300])

    try:
        parsed = json.loads(cleaned)
        valid, err = validate_image_analysis_contract(parsed)
        if valid:
            print(f"[LLM-Image] 契约校验通过")
            return normalize_image_analysis_payload(parsed)
        print(f"[LLM-Image] 契约校验失败: {err}")
    except json.JSONDecodeError as e:
        print(f"[LLM-Image] JSON解析失败: {e}")
    except Exception as e:
        print(f"[LLM-Image] 解析异常: {e}")

    try:
        json_match = re.search(r'\{[\s\S]*\}', current_text or "")
        if json_match:
            parsed = json.loads(json_match.group())
            valid, err = validate_image_analysis_contract(parsed)
            if valid:
                print(f"[LLM-Image] 备用解析成功")
                return normalize_image_analysis_payload(parsed)
    except Exception as e2:
        print(f"[LLM-Image] 备用解析也失败: {e2}")

    print(f"[LLM-Image] 最终解析失败，返回兜底")
    return normalize_image_analysis_payload({
        "drawing_features": ["模型未返回可解析的绘画分析结果"]
    })


# ═══════════════════════════════════════════════════════════════
# 视频分析契约（Batch B：webcam + canvas）
# ═══════════════════════════════════════════════════════════════

def validate_video_analysis_contract(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """校验视频分析输出契约"""
    if not isinstance(payload, dict):
        return False, "payload不是对象"
    for field in ["expression_observation", "process_observation"]:
        if field not in payload:
            return False, f"缺少字段: {field}"
        value = payload[field]
        if not isinstance(value, list):
            return False, f"{field}必须是数组"
        if not all(isinstance(x, str) for x in value):
            return False, f"{field}必须是字符串数组"
    return True, ""


def normalize_video_analysis_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将视频分析结果转换为内部兼容格式"""
    if not isinstance(payload, dict):
        return {"raw_response": str(payload)}
    return {
        "analysis": {
            "expression_observation": payload.get("expression_observation", []),
            "process_observation": payload.get("process_observation", [])
        },
        "questions_for_user": [],
        "psychological_guesstimates": []
    }


def parse_video_analysis_response(response: str) -> Dict[str, Any]:
    """解析视频分析响应（Batch B）"""
    current_text = response or ""
    cleaned = clean_json_text(current_text)
    print(f"[LLM-Video] 清理后响应 ({len(cleaned)} 字符):")
    print(cleaned[:300])

    try:
        parsed = json.loads(cleaned)
        valid, err = validate_video_analysis_contract(parsed)
        if valid:
            print(f"[LLM-Video] 契约校验通过")
            return normalize_video_analysis_payload(parsed)
        print(f"[LLM-Video] 契约校验失败: {err}")
    except json.JSONDecodeError as e:
        print(f"[LLM-Video] JSON解析失败: {e}")
    except Exception as e:
        print(f"[LLM-Video] 解析异常: {e}")

    try:
        json_match = re.search(r'\{[\s\S]*\}', current_text or "")
        if json_match:
            parsed = json.loads(json_match.group())
            valid, err = validate_video_analysis_contract(parsed)
            if valid:
                print(f"[LLM-Video] 备用解析成功")
                return normalize_video_analysis_payload(parsed)
    except Exception as e2:
        print(f"[LLM-Video] 备用解析也失败: {e2}")

    print(f"[LLM-Video] 最终解析失败，返回兜底")
    return normalize_video_analysis_payload({
        "expression_observation": ["模型未返回可解析的表情分析结果"],
        "process_observation": ["模型未返回可解析的过程分析结果"]
    })


# ═══════════════════════════════════════════════════════════════
# 兼容旧接口：多模态分析解析（保留）
# ═══════════════════════════════════════════════════════════════

def validate_multimodal_analysis_contract(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """校验多模态分析输出契约 —— 直接校验裸 analysis 对象（字符串数组格式）"""
    if not isinstance(payload, dict):
        return False, "payload不是对象"
    for field in ["drawing_features", "expression_observation", "process_observation"]:
        if field not in payload:
            return False, f"缺少字段: {field}"
        value = payload[field]
        if not isinstance(value, list):
            return False, f"{field}必须是数组"
        if not all(isinstance(x, str) for x in value):
            return False, f"{field}必须是字符串数组"
    return True, ""


def normalize_multimodal_analysis_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将多模态分析结果统一转换为内部兼容格式"""
    if not isinstance(payload, dict):
        return {"raw_response": str(payload)}
    return {
        "analysis": payload,
        "questions_for_user": [],
        "psychological_guesstimates": []
    }


def parse_multimodal_analysis_response(response: str) -> Dict[str, Any]:
    """解析多模态分析响应：清理 + 解析 + 基本兜底"""
    current_text = response or ""
    cleaned = clean_json_text(current_text)
    print(f"[LLM-Multimodal] 清理后响应 ({len(cleaned)} 字符):")
    print(cleaned[:300])

    try:
        parsed = json.loads(cleaned)
        valid, err = validate_multimodal_analysis_contract(parsed)
        if valid:
            print(f"[LLM-Multimodal] 分析JSON契约校验通过")
            return normalize_multimodal_analysis_payload(parsed)
        print(f"[LLM-Multimodal] 契约校验失败: {err}")
    except json.JSONDecodeError as e:
        print(f"[LLM-Multimodal] JSON解析失败: {e}")
    except Exception as e:
        print(f"[LLM-Multimodal] 解析异常: {e}")

    try:
        json_match = re.search(r'\{[\s\S]*\}', current_text or "")
        if json_match:
            parsed = json.loads(json_match.group())
            valid, err = validate_multimodal_analysis_contract(parsed)
            if valid:
                print(f"[LLM-Multimodal] 备用解析成功")
                return normalize_multimodal_analysis_payload(parsed)
            print(f"[LLM-Multimodal] 备用契约校验失败: {err}")
    except Exception as e2:
        print(f"[LLM-Multimodal] 备用解析也失败: {e2}")

    print(f"[LLM-Multimodal] 分析结果最终解析失败，返回unknown兜底")
    return normalize_multimodal_analysis_payload({
        "drawing_features": ["模型未返回可解析的分析结果"],
        "expression_observation": [],
        "process_observation": []
    })


# ═══════════════════════════════════════════════════════════════
# 完整分析契约（保留，用于需要 questions/hypotheses 的场景）
# ═══════════════════════════════════════════════════════════════

def validate_analysis_contract(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """校验分析输出契约 —— Schema 冻结版本：仅支持嵌套格式（analysis 对象）"""
    if not isinstance(payload, dict):
        return False, "payload不是对象"

    allowed_top_keys = {"status", "data", "error"}
    extra_keys = set(payload.keys()) - allowed_top_keys
    if extra_keys:
        return False, f"存在额外顶层字段: {sorted(extra_keys)}"

    status = payload.get("status")
    if status not in {"ok", "unknown", "error"}:
        return False, "status必须是ok/unknown/error"

    if status == "ok":
        data = payload.get("data")
        if not isinstance(data, dict):
            return False, "status=ok时data必须是对象"

        # 冻结格式：必须包含 analysis 对象（嵌套格式）
        if not isinstance(data.get("analysis"), dict):
            return False, "data 必须包含 analysis 对象（嵌套格式，Schema 已冻结）"

        required_data_keys = {"analysis", "questions_for_user", "psychological_guesstimates"}
        missing_data_keys = required_data_keys - set(data.keys())
        if missing_data_keys:
            return False, f"data缺少字段: {sorted(missing_data_keys)}"
        if not isinstance(data.get("questions_for_user"), list):
            return False, "data.questions_for_user必须是数组"
        if not isinstance(data.get("psychological_guesstimates"), list):
            return False, "data.psychological_guesstimates必须是数组"
        if not all(isinstance(x, str) for x in data.get("questions_for_user", [])):
            return False, "data.questions_for_user必须是字符串数组"
        if not all(isinstance(x, str) or isinstance(x, dict) for x in data.get("psychological_guesstimates", [])):
            return False, "data.psychological_guesstimates元素类型不合法"
        return True, ""

    # unknown/error
    err = payload.get("error")
    if not isinstance(err, dict):
        return False, "status=unknown/error时error必须是对象"
    if not isinstance(err.get("code"), str) or not isinstance(err.get("message"), str):
        return False, "error必须包含字符串code和message"
    return True, ""


def normalize_analysis_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将契约统一转换为内部兼容格式 —— Schema 冻结版本：仅支持嵌套格式"""
    if not isinstance(payload, dict):
        return {"raw_response": str(payload)}

    status = payload.get("status")
    if status == "ok" and isinstance(payload.get("data"), dict):
        data = payload["data"]
        return {
            "analysis": data.get("analysis", {}),
            "questions_for_user": data.get("questions_for_user", []),
            "psychological_guesstimates": data.get("psychological_guesstimates", [])
        }

    if status in {"unknown", "error"}:
        err = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
        msg = err.get("message", "模型未返回可解析结构化结果")
        return {
            "analysis": {},
            "questions_for_user": [
                "你最想让画里的哪个部分发生变化？为什么？",
                "在这个场景里，你最在意的感受是什么？"
            ],
            "psychological_guesstimates": [
                f"模型返回未知状态：{msg}"
            ]
        }

    # 扁平化/旧格式兼容已移除（Schema 已冻结）
    return {"raw_response": str(payload)}


def parse_analysis_response_with_contract(response: str) -> Dict[str, Any]:
    """解析分析响应：清理 + 解析 + 基本兜底"""
    current_text = response or ""

    cleaned = clean_json_text(current_text)
    print(f"[LLM] 清理后响应 ({len(cleaned)} 字符):")
    print(cleaned[:300])

    try:
        parsed = json.loads(cleaned)
        valid, err = validate_analysis_contract(parsed)
        if valid:
            print(f"[LLM] 分析JSON契约校验通过")
            return normalize_analysis_payload(parsed)
        print(f"[LLM] 契约校验失败: {err}")
    except json.JSONDecodeError as e:
        print(f"[LLM] JSON解析失败: {e}")
    except Exception as e:
        print(f"[LLM] 解析异常: {e}")

    # 备用提取
    try:
        json_match = re.search(r'\{[\s\S]*\}', current_text or "")
        if json_match:
            parsed = json.loads(json_match.group())
            valid, err = validate_analysis_contract(parsed)
            if valid:
                print(f"[LLM] 备用解析成功")
                return normalize_analysis_payload(parsed)
            print(f"[LLM] 备用契约校验失败: {err}")
    except Exception as e2:
        print(f"[LLM] 备用解析也失败: {e2}")

    print(f"[LLM] 分析结果最终解析失败，返回unknown兜底")
    return normalize_analysis_payload({
        "status": "unknown",
        "error": {
            "code": "ANALYSIS_PARSE_FAILED",
            "message": "无法解析模型响应"
        }
    })


def validate_final_report_contract(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """校验最终报告输出契约（扁平化版本）"""
    if not isinstance(payload, dict):
        return False, "payload不是对象"

    # 兼容旧格式：无 status 包装，直接是报告对象
    if "status" not in payload:
        if isinstance(payload.get("summary"), str):
            return True, ""
        return False, "缺少status且summary不是字符串"

    allowed_top_keys = {"status", "data", "error"}
    extra = set(payload.keys()) - allowed_top_keys
    if extra:
        return False, f"存在额外顶层字段: {sorted(extra)}"

    status = payload.get("status")
    if status not in {"ok", "unknown", "error"}:
        return False, "status必须是ok/unknown/error"

    if status == "ok":
        data = payload.get("data")
        if not isinstance(data, dict):
            return False, "status=ok时data必须是对象"
        if not isinstance(data.get("summary"), str):
            return False, "data.summary必须是字符串"
        return True, ""

    err = payload.get("error")
    if not isinstance(err, dict):
        return False, "status=unknown/error时error必须是对象"
    if not isinstance(err.get("code"), str) or not isinstance(err.get("message"), str):
        return False, "error必须包含字符串code和message"
    return True, ""


def normalize_final_report_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    统一最终报告结构为扁平化版本：
    - summary / creative_insights / suggested_explorations
    """
    # 1) 解包 status/data 契约
    if isinstance(payload, dict) and payload.get("status") == "ok" and isinstance(payload.get("data"), dict):
        report = dict(payload["data"])
    elif isinstance(payload, dict) and payload.get("status") in {"unknown", "error"}:
        err = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
        msg = err.get("message", "最终报告生成未完全成功")
        report = {
            "summary": "本次回顾生成未完全成功，以下为兜底结果。",
            "creative_insights": [msg],
            "suggested_explorations": ["建议稍后重试，或在观察伙伴面板查看原始日志。"]
        }
    else:
        report = dict(payload) if isinstance(payload, dict) else {}

    # 2) 确保三个核心字段存在
    if not isinstance(report.get("summary"), str) or not report.get("summary").strip():
        report["summary"] = "创作回顾已完成，部分细节待补充。"
    if not isinstance(report.get("creative_insights"), list):
        report["creative_insights"] = []
    if not isinstance(report.get("suggested_explorations"), list):
        report["suggested_explorations"] = []

    return report


def parse_final_report_with_contract(response: str) -> Dict[str, Any]:
    """解析最终报告：清理 + 解析 + 基本兜底 + 前端字段归一化"""
    current_text = response or ""

    cleaned = clean_json_text(current_text)
    print(f"[LLM] 清理后响应 ({len(cleaned)} 字符):")
    print(cleaned[:300])

    try:
        parsed = json.loads(cleaned)
        valid, err = validate_final_report_contract(parsed)
        if valid:
            print(f"[LLM] Final Report 契约校验通过")
            return normalize_final_report_result(parsed)
        print(f"[LLM] Final Report 契约校验失败: {err}")
    except json.JSONDecodeError as e:
        print(f"[LLM] JSON解析失败: {e}")
    except Exception as e:
        print(f"[LLM] 解析异常: {e}")

    # 备用提取
    try:
        json_match = re.search(r'\{[\s\S]*\}', current_text or "")
        if json_match:
            parsed = json.loads(json_match.group())
            valid, err = validate_final_report_contract(parsed)
            if valid:
                print(f"[LLM] 备用解析成功")
                return normalize_final_report_result(parsed)
            print(f"[LLM] 备用契约校验失败: {err}")
    except Exception as e2:
        print(f"[LLM] 备用解析也失败: {e2}")

    print(f"[LLM] Final Report 最终解析失败，返回兜底")
    return normalize_final_report_result({
        "status": "unknown",
        "error": {
            "code": "FINAL_REPORT_PARSE_FAILED",
            "message": "无法解析模型响应"
        }
    })


def standardize_analysis_result(result: Dict) -> Dict:
    """标准化分析结果字段，确保与 main.py 兼容 —— Schema 冻结版本：仅支持嵌套格式"""
    standardized = {
        "analysis": {},  # 保持兼容：下游代码期望 analysis 对象
        "questions": [],
        "hypotheses": [],
        "raw_response": result.get("raw_response", "")
    }

    # ── 处理 analysis 数据（仅嵌套格式）──
    if isinstance(result.get("analysis"), dict):
        standardized["analysis"] = result["analysis"]

    # 处理 questions 字段
    questions = result.get("questions_for_user", [])
    if isinstance(questions, list):
        standardized["questions"] = questions

    # 处理 hypotheses 字段
    hypotheses = result.get("psychological_guesstimates", [])
    if isinstance(hypotheses, list):
        standardized["hypotheses"] = [
            {"description": h, "confidence": "medium"} if isinstance(h, str) else h
            for h in hypotheses
        ]

    # 提取分析摘要（用于对话历史）
    analysis = standardized["analysis"]
    drawing_features = analysis.get("drawing_features", [])
    summary_parts = []
    if isinstance(drawing_features, list):
        for item in drawing_features:
            if item:
                summary_parts.append(item)
    elif isinstance(drawing_features, dict):
        # 兼容旧格式（对象形式）
        for key, value in drawing_features.items():
            if value:
                summary_parts.append(f"{key}: {value}")
    standardized["analysis_summary"] = " | ".join(summary_parts) if summary_parts else "分析完成"

    return standardized


def parse_edit_instructions(response: str, repair_fn=None) -> List[Dict]:
    """解析编辑指令（严格契约 + 旧格式兼容 + 有界修复）"""
    from services.llm.prompts import build_repair_prompt

    current_text = response or ""
    last_error = "unknown"

    for attempt in range(3):
        cleaned = clean_json_text(current_text)
        variations: List[Dict] = []
        try:
            data = json.loads(cleaned)
            # 新契约: {"status":"ok","data":[...]}
            if isinstance(data, dict) and data.get("status") == "ok" and isinstance(data.get("data"), list):
                variations = data.get("data", [])
            # 旧格式兼容
            elif isinstance(data, list):
                variations = data
            elif isinstance(data, dict):
                for key in ["variations", "edits", "variants", "results", "data"]:
                    if isinstance(data.get(key), list):
                        variations = data.get(key, [])
                        break

            if variations:
                validated = validate_variations(variations)
                if validated:
                    print(f"[LLM] 编辑指令解析成功: {len(validated)} 个变体 (attempt={attempt})")
                    return validated
            last_error = "未找到有效变体数组"
        except Exception as e:
            last_error = str(e)
            print(f"[LLM] 编辑指令解析失败 (attempt={attempt}): {e}")

        # 最后一次不再修复
        if attempt >= 2:
            break

        if repair_fn:
            repair_prompt = build_repair_prompt(current_text, last_error)
            repaired = repair_fn(repair_prompt)
            if repaired:
                current_text = repaired

    print(f"[LLM] 警告: 编辑指令解析失败，使用默认值")
    return get_default_variations()


def validate_variations(variations: List[Dict]) -> List[Dict]:
    """验证并修复变体数据"""
    validated = []
    defaults = get_default_variations()

    for i, var in enumerate(variations[:3]):
        if not isinstance(var, dict):
            validated.append(defaults[i])
            continue

        name = var.get("name") if var.get("name") and var.get("name") != "string" else defaults[i]["name"]
        description = var.get("description") if var.get("description") and var.get("description") != "string" else defaults[i]["description"]
        edit_prompt = var.get("edit_prompt") if var.get("edit_prompt") and var.get("edit_prompt") != "string" else defaults[i]["edit_prompt"]
        color_prompt = var.get("color_prompt") if var.get("color_prompt") and var.get("color_prompt") != "string" else defaults[i]["color_prompt"]

        validated.append({
            "name": name,
            "description": description,
            "edit_prompt": edit_prompt,
            "color_prompt": color_prompt
        })

    # 补充默认值
    while len(validated) < 3:
        validated.append(defaults[len(validated)])

    return validated[:3]


def get_default_variations() -> List[Dict]:
    """获取默认变体"""
    return [
        {
            "name": "温暖庇护",
            "description": "用温暖的色调和安全感增强画面",
            "edit_prompt": "Preserve original composition and character scale unchanged, minimal edits only. Add a small transparent umbrella and slightly soften rain stroke contrast around the head and shoulders. Keep all original linework and object layout.",
            "color_prompt": "Keep original palette, add subtle warm highlights (soft amber) only in local areas"
        },
        {
            "name": "雨中希望",
            "description": "在雨景中增添希望和明亮元素",
            "edit_prompt": "Preserve original composition, character position and scale unchanged, minimal edits only. Keep rain and cloud structure, add a gentle light break near cloud edge and a small reflective highlight on ground. Do not redraw scene.",
            "color_prompt": "Slightly increase brightness in cool blues with tiny fresh green accents, no dramatic color shift"
        },
        {
            "name": "宁静平衡",
            "description": "创造平静和谐的中性氛围",
            "edit_prompt": "Preserve original composition and all main contours unchanged, minimal edits only. Slightly regularize rain spacing and add a small practical raincoat detail while keeping the character pose intact. Maintain original scene geometry.",
            "color_prompt": "Neutral soft grays and gentle blue tint, very low saturation change"
        }
    ]
