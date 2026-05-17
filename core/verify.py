"""
事后验证模块 — 拿 Agent 提取的值，去 OCR 原文里搜，确认不是编的

原理：
  Agent 输出 "检测道路": "新华路"
  → 程序在已读文件的 OCR 文字中搜 "新华路"
  → 搜到了 → verified ✓
  → 搜不到 → 标记 ⚠ 需人工复核

不做语义判断，只做字符串匹配——简单、确定、不会错。
"""

from typing import Any


def verify_field(value: str, ocr_texts: dict[str, str]) -> dict:
    """
    验证单个字段值是否能在 OCR 原文中找到

    Args:
        value: 提取出的字段值
        ocr_texts: {文件路径: OCR文字内容}

    Returns:
        {
            "verified": True/False,
            "found_in": ["文件1", "文件2"],  # 在哪份文件中找到了
            "matched_text": "...",          # 匹配到的原文片段
        }
    """
    if not value or not value.strip():
        return {"verified": None, "found_in": [], "matched_text": "", "reason": "字段为空，无需验证"}

    value_clean = value.strip()

    # 太短的值不验（如 "无"、"0"、"未知"）
    if len(value_clean) < 2:
        return {"verified": None, "found_in": [], "matched_text": "", "reason": "值过短，跳过后验"}

    found_in = []
    best_match = ""

    for file_path, text in ocr_texts.items():
        if not text or text.startswith("[错误]") or text.startswith("[跳过]"):
            continue

        # 多粒度搜索
        # 1. 精确匹配整个值
        if value_clean in text:
            found_in.append(file_path)
            # 截取匹配位置附近的内容
            idx = text.index(value_clean)
            start = max(0, idx - 20)
            end = min(len(text), idx + len(value_clean) + 20)
            best_match = text[start:end]
            continue

        # 2. 按关键数字匹配（如 "1250米" → 搜 "1250"）
        import re
        num_match = re.search(r"(\d+\.?\d*)", value_clean)
        if num_match:
            num = num_match.group(1)
            if len(num) >= 3 and num in text:
                if file_path not in found_in:
                    found_in.append(file_path)
                if not best_match:
                    idx = text.index(num)
                    start = max(0, idx - 20)
                    end = min(len(text), idx + 40)
                    best_match = text[start:end]

    if found_in:
        return {
            "verified": True,
            "found_in": found_in,
            "matched_text": best_match,
        }
    else:
        return {
            "verified": False,
            "found_in": [],
            "matched_text": "",
            "reason": f"值「{value_clean}」在已读文件中未找到匹配",
        }


def verify_extraction(
    extracted: dict[str, Any],
    ocr_cache: dict[str, str],
) -> dict[str, Any]:
    """
    对提取结果做全面验证

    Args:
        extracted: Agent 输出的提取结果 {字段: 值}
        ocr_cache: 已读文件的 OCR 文字缓存 {文件路径: 文字}

    Returns:
        带验证标记的结果：
        {
            "提取结果": {原样},
            "验证": {
                "项目名称": {"verified": True, "found_in": ["合同.txt"], ...},
                "开始时间": {"verified": True, "found_in": ["合同.txt"], ...},
                "检测道路": {"verified": False, "found_in": [], ...},  ← 可能编的
            },
            "已读文件": [...],
            "置信度评估": { ... }
        }
    """
    # 过滤出真正的字段（去掉 _ 开头的元数据和"提取结果""已读文件"等结构键）
    meta_keys = {"提取结果", "已读文件", "_folder", "_path", "_type", "_status", "_error", "_raw"}
    fields = {k: v for k, v in extracted.items()
              if not k.startswith("_") and k not in meta_keys}

    verification = {}
    verified_count = 0
    not_found_count = 0
    skipped_count = 0

    for field, value in fields.items():
        result = verify_field(str(value) if value else "", ocr_cache)
        verification[field] = result

        if result["verified"] is True:
            verified_count += 1
        elif result["verified"] is False:
            not_found_count += 1
        else:
            skipped_count += 1

    # 置信度评估
    total_fields = len(fields) or 1
    if not_found_count == 0:
        confidence = "高"
        need_review = False
    elif not_found_count <= max(1, total_fields * 0.2):
        confidence = "中"
        need_review = True
    else:
        confidence = "低"
        need_review = True

    return {
        "提取结果": fields,
        "验证": verification,
        "已读文件": list(ocr_cache.keys()),
        "置信度评估": {
            "等级": confidence,
            "需人工复核": need_review,
            "已验证字段数": verified_count,
            "未找到原文字段数": not_found_count,
            "跳过字段数": skipped_count,
        },
    }
