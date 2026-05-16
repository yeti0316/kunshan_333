"""
模板加载模块 — 从 templates.yaml 读取项目类型模板
"""

import yaml
from pathlib import Path
from typing import Any


def load_templates(yaml_path: str | None = None) -> list[dict]:
    """
    加载所有项目类型模板
    
    Args:
        yaml_path: 模板文件路径，默认读取 config/templates.yaml
        
    Returns:
        模板列表，每个模板是一个 dict
    """
    if yaml_path is None:
        yaml_path = Path(__file__).parent.parent / "config" / "templates.yaml"

    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    templates = data.get("模板列表", [])
    if not templates:
        raise ValueError("模板文件为空或格式不正确")

    return templates


def match_template(folder_name: str, file_names: list[str], templates: list[dict]) -> dict | None:
    """
    根据文件夹名和文件名，匹配最合适的模板
    
    匹配策略:
    1. 优先检查文件夹名是否包含模板类型或别名关键词
    2. 其次检查文件名是否匹配模板的"常见文件"类型
    3. 返回最匹配的模板，或 None
    
    Args:
        folder_name: 项目文件夹名称
        file_names: 项目文件夹下的文件名列表
        templates: 模板列表
        
    Returns:
        匹配到的模板 dict，或 None
    """
    best_match = None
    best_score = 0

    for tmpl in templates:
        score = 0
        type_name = tmpl.get("类型", "")
        aliases = tmpl.get("别名", [])

        # 检查文件夹名是否包含类型名或别名
        keywords = [type_name] + aliases
        for kw in keywords:
            if kw and kw in folder_name:
                score += 10

        # 检查文件名是否匹配常见文件类型
        common_files = tmpl.get("常见文件", [])
        for cf in common_files:
            for fn in file_names:
                if cf in fn:
                    score += 3

        if score > best_score:
            best_score = score
            best_match = tmpl

    return best_match if best_score > 0 else None


def get_all_field_names(template: dict) -> list[str]:
    """
    获取模板的所有字段（必填 + 选填）
    """
    required = template.get("必填", [])
    optional = template.get("选填", [])
    return required + optional
