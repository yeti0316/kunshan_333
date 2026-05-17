"""
ReAct Agent 工具集 — 只保留最必要的两个工具
read_document 会自动查缓存，避免重复读取同一份文件
"""

import os
from pathlib import Path

from langchain_core.tools import tool

from core.extractor import extract_text
from core.ocr_cache import get_cache


@tool
def list_project_files(project_path: str) -> str:
    """列出项目下的文件（目录则列出所有子文件，单文件则返回该文件）"""
    path = Path(project_path)
    if not path.exists():
        return f"[错误] 路径不存在: {project_path}"

    # 如果是文件，直接返回
    if path.is_file():
        size = path.stat().st_size
        size_str = f"{size//1024}KB" if size > 1024 else f"{size}B"
        return f"{path.name}  ({size_str})"

    # 如果是目录
    if not path.is_dir():
        return f"[错误] 不是文件也不是目录: {project_path}"

    files = []
    for entry in sorted(path.rglob("*")):
        if entry.is_file():
            name = entry.name
            if name.startswith("."):
                continue
            if entry.suffix.lower() in (".tmp", ".temp", ".lnk"):
                continue
            rel_path = str(entry.relative_to(path))
            size = entry.stat().st_size
            size_str = f"{size//1024}KB" if size > 1024 else f"{size}B"
            files.append(f"{rel_path}  ({size_str})")

    if not files:
        return "[空] 文件夹内没有文件"

    return "\n".join(files)


@tool
def read_document(file_path: str, max_pages: int = 1) -> str:
    """读取文档内容并返回文字。
    
    支持 PDF / Word (.docx) / 图片 (.png .jpg .bmp)
    
    - 文字型 PDF → 直接提取文字
    - 扫描件 PDF → 自动切换到 OCR
    - Word 文档 → 解析文字
    - 图片 → OCR 识别
    
    会自动缓存结果，同一文件重复读取直接返回缓存。
    
    Args:
        file_path: 文件完整路径
        max_pages: 最多读取前几页（默认 1 页），关键信息通常在第 1 页
    """
    if not os.path.exists(file_path):
        return f"[错误] 文件不存在: {file_path}"

    # 查缓存
    cache = get_cache()
    cached = cache.get(file_path)
    if cached is not None:
        return cached

    # 执行提取
    try:
        text = extract_text(file_path, max_pages=max_pages)
        # 写缓存（非关键错误不影响使用）
        try:
            method = "direct" if not text.startswith("[") else "ocr"
            cache.set(file_path, text, method=method)
        except Exception:
            pass
        return text
    except Exception as e:
        return f"[错误] 读取失败: {e}"
