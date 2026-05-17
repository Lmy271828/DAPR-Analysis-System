#!/usr/bin/env python3
"""
DAPR 知识库伦理一致性检查脚本

用途：在提交前自动检查知识库文档是否包含违规内容
违规类型：
  - 病理化语言（诊断术语、精神疾病标签）
  - 确定性心理断言（"这意味着..." "这说明你有..."）
  - 评分/量化语言（0-3分、风险等级）
  - 伪科学表述

使用方式：
  python scripts/ethics_check.py [files...]
  无参数时检查 docs/dapr_knowledge_base/ 下所有 .md 文件

退出码：
  0 - 检查通过
  1 - 发现违规内容

安装为 Git pre-commit hook：
  cp scripts/ethics_check.py .git/hooks/pre-commit
  chmod +x .git/hooks/pre-commit
"""

import re
import sys
from pathlib import Path

# ───────────────────────────────────────────────
# 违规规则定义
# ───────────────────────────────────────────────

# 1. 病理化/诊断术语（本系统定位下禁止使用）
PATHOLOGICAL_TERMS = [
    r"\b抑郁症\b", r"\b焦虑症\b", r"\bPTSD\b", r"\b创伤后应激\b",
    r"\b人格障碍\b", r"\b精神分裂症\b", r"\b双相情感\b", r"\b自闭症\b",
    r"\b注意力缺陷\b", r"\b多动症\b", r"\b强迫症\b", r"\b恐惧症\b",
    r"\b精神障碍\b", r"\b心理疾病\b", r"\b精神病\b",
    r"\b自杀倾向\b", r"\b自伤行为\b", r"\b自残\b",
    r"\b病态\b", r"\b异常心理\b", r"\b心理变态\b",
]

# 2. 确定性心理断言（禁止以确定语气将绘画元素与心理状态关联）
DETERMINISTIC_PATTERNS = [
    r"这意味着[他她它]?有",
    r"这说明[他她它]?",
    r"反映[了出]?[他她它]?的?.*?(?:问题|障碍|疾病|缺陷)",
    r"表明[他她它]?患有",
    r"可以诊断[为出]?",
    r"证明[他她它]?",
    r"[肯定一定必然]是",
]

# 3. 评分/量化语言（本系统不使用评分）
SCORING_PATTERNS = [
    r"\d+分制", r"0-[123]分", r"[零一二三四五]分制",
    r"风险等级[为是]?[低中高]", r"[低中高]风险",
    r"评分标准.*?\d+", r"量化评估",
]

# 4. 伪科学/过度断言
PSEUDOSCIENCE_PATTERNS = [
    r"[绝对完全]准确", r"[10十]0%准确", r"准确率[高达达].*?\d+%",
    r"[能够可以].*?诊断", r"[用于作为].*?筛查工具",
]

# 5. 需要人工复核的敏感表述（警告级别，不阻断）
WARNING_PATTERNS = [
    r"防御机制.*?(?:弱|差|不足|缺失)",
    r"自我力量.*?(?:弱|差|低)",
    r"应对能力.*?(?:差|不足|低下)",
    r"情绪调节.*?(?:障碍|问题|困难)",
]

ALL_RULES = {
    "病理化术语": (PATHOLOGICAL_TERMS, "error"),
    "确定性断言": (DETERMINISTIC_PATTERNS, "error"),
    "评分量化": (SCORING_PATTERNS, "error"),
    "伪科学表述": (PSEUDOSCIENCE_PATTERNS, "error"),
    "敏感表述": (WARNING_PATTERNS, "warning"),
}

# 白名单：某些上下文下允许出现的术语
ALLOWLIST_CONTEXTS = [
    # "禁止输出..." / "禁止病理化语言" 等系统指令中的反面示例
    (r"禁止.*?(?:输出|病理化|诊断|治疗)", None),
    (r"禁止.*?(?:抑郁|焦虑|PTSD|创伤|自杀|自伤|诊断|病理|障碍|治疗)", None),
    # "本系统不使用评分" / "不足以作为" / "未必是" 等否定性表述
    (r"(?:不|未|无|不足).*?(?:使用|采用|进行|作为|足以|用于).*?(?:评分|诊断|评估|筛查|工具)", None),
    (r"未必是", None),
    # 学术引用中的术语（带年份的引用）
    (r"\(\d{4}\)", None),
    # Markdown 引用块中的内容
    (r">\s*.*?(?:抑郁|焦虑|诊断|PTSD|创伤)", None),
    # Markdown 表格中的学术数据（含竖线分隔符）
    (r"\|.*?(?:评分|应对能力|压力分|资源分).*?\|", None),
    # "这意味着..." 在引号内作为反面示例
    (r"['\"].*?这意味着.*?['\"]|禁止.*?(?:这意味着|这说明)", None),
    # 标题中的学术术语
    (r"^#{1,6}\s*.*?(?:评分|评估|诊断|筛查)", None),
]


def is_allowlisted(line: str, match_text: str) -> bool:
    """检查匹配文本是否在白名单上下文中"""
    for pattern, _ in ALLOWLIST_CONTEXTS:
        if re.search(pattern, line):
            return True
    return False


def check_file(filepath: Path) -> list:
    """检查单个文件，返回违规列表"""
    violations = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return [("error", 0, f"无法读取文件: {e}")]

    lines = content.split("\n")
    for line_no, line in enumerate(lines, 1):
        for category, (patterns, level) in ALL_RULES.items():
            for pattern in patterns:
                for match in re.finditer(pattern, line):
                    match_text = match.group(0)
                    if is_allowlisted(line, match_text):
                        continue
                    violations.append((
                        level,
                        line_no,
                        f"[{category}] {match_text}",
                        line.strip()
                    ))
    return violations


def main():
    if len(sys.argv) > 1:
        files = [Path(p) for p in sys.argv[1:]]
    else:
        kb_dir = Path("docs/dapr_knowledge_base")
        if not kb_dir.exists():
            print(f"❌ 知识库目录不存在: {kb_dir}")
            sys.exit(1)
        files = sorted(kb_dir.glob("*.md"))

    if not files:
        print("未找到需要检查的文件")
        sys.exit(0)

    total_errors = 0
    total_warnings = 0

    print(f"🔍 检查 {len(files)} 个知识库文件...\n")

    for filepath in files:
        if not filepath.exists():
            print(f"⚠️  跳过不存在: {filepath}")
            continue

        violations = check_file(filepath)
        errors = [v for v in violations if v[0] == "error"]
        warnings = [v for v in violations if v[0] == "warning"]

        if errors or warnings:
            print(f"📄 {filepath}")
            for level, line_no, desc, line_text in errors:
                print(f"   ❌ 第{line_no:3d}行: {desc}")
                print(f"      → {line_text[:100]}")
                total_errors += 1
            for level, line_no, desc, line_text in warnings:
                print(f"   ⚠️  第{line_no:3d}行: {desc}")
                print(f"      → {line_text[:100]}")
                total_warnings += 1
            print()

    print("─" * 50)
    if total_errors == 0 and total_warnings == 0:
        print("✅ 所有文件通过伦理一致性检查")
        sys.exit(0)
    elif total_errors == 0:
        print(f"⚠️  发现 {total_warnings} 个警告（需人工复核），0 个错误")
        print("   建议 Review 后决定是否通过")
        sys.exit(0)
    else:
        print(f"❌ 发现 {total_errors} 个错误，{total_warnings} 个警告")
        print("   错误必须修复后才能提交")
        sys.exit(1)


if __name__ == "__main__":
    main()
