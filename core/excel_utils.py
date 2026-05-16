"""
Excel 导出模块 — 将提取结果汇总导出为 Excel 文件
"""

import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


def results_to_excel(
    json_path: str,
    output_path: str,
    template_fields: dict[str, list[str]] | None = None,
) -> str:
    """
    将 JSON 结果文件转换为 Excel

    Args:
        json_path: 输入的 JSON 文件路径
        output_path: 输出的 Excel 文件路径
        template_fields: 可选，字段顺序模板 {项目类型: [字段列表]}

    Returns:
        输出的 Excel 文件路径
    """
    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    if not results:
        raise ValueError("JSON 文件为空，没有可导出的数据")

    wb = Workbook()
    ws = wb.active
    ws.title = "项目汇总"

    # ---- 收集所有字段 ----
    all_fields = ["项目类型"]
    field_set = set(all_fields)
    for item in results:
        for k in item.keys():
            if k not in field_set:
                all_fields.append(k)
                field_set.add(k)

    # ---- 样式 ----
    header_font = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_alignment = Alignment(vertical="top", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # ---- 写表头 ----
    for col_idx, field in enumerate(all_fields, 1):
        cell = ws.cell(row=1, column=col_idx, value=field)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # ---- 写数据 ----
    for row_idx, item in enumerate(results, 2):
        # 第一列：项目类型
        cell = ws.cell(row=row_idx, column=1, value=item.get("项目类型", ""))
        cell.alignment = cell_alignment
        cell.border = thin_border

        for col_idx, field in enumerate(all_fields[1:], 2):
            value = item.get(field, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=2)
            elif value is None:
                value = ""
            else:
                value = str(value)
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = cell_alignment
            cell.border = thin_border

    # ---- 列宽自适应（最大 50 字符） ----
    for col_idx, field in enumerate(all_fields, 1):
        max_len = len(field) * 2  # 中文字符占位更宽
        for row_idx in range(2, len(results) + 2):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val:
                # 中文字符算 2 个宽度
                char_len = sum(2 if ord(c) > 127 else 1 for c in str(val))
                max_len = max(max_len, min(char_len, 50))
        ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else "A"].width = max_len + 2

    # ---- 冻结首行 ----
    ws.freeze_panes = "A2"

    wb.save(output_path)
    return output_path


def merge_json_results(results: list[dict], output_path: str) -> str:
    """
    将多个项目提取结果合并为一个 JSON 文件
    
    Args:
        results: 项目结果列表
        output_path: 输出的 JSON 文件路径
        
    Returns:
        输出的 JSON 文件路径
    """
    output_path = Path(output_path).resolve()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return str(output_path)
