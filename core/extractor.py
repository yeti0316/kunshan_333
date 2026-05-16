"""
文档文字提取模块
智能策略：先尝试直接提取文字，文字太少才走 OCR
对 PDF 支持只读前 N 页（关键信息通常在前 1-2 页）

OCR 模式：
  - local: 直接加载 PaddleOCR（默认）
  - http:  调用远程 OCR 服务（见 ocr_server.py，模型常驻，避免重复加载）
  
在 .env 中设置：
  OCR_MODE=http
  OCR_SERVICE_URL=http://localhost:5000
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import fitz  # PyMuPDF

# ============ OCR 配置 ============

OCR_MODE = os.getenv("OCR_MODE", "local")  # "local" | "http"
OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://localhost:5000")
OCR_THRESHOLD = 50  # 直接提取文字少于这个数 → 判定为扫描件，走 OCR

# ============ 本地 OCR（直接加载 PaddleOCR） ============

try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None

_ocr: Optional[PaddleOCR] = None


def get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        if PaddleOCR is None:
            raise ImportError("paddleocr 未安装，请运行: pip install paddleocr")
        _ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    return _ocr


# ============ HTTP 远程 OCR ============

def _ocr_via_http(file_path: str, max_pages: int = 2) -> str:
    """通过 HTTP 调用远程 OCR 服务"""
    try:
        import httpx
    except ImportError:
        return f"[错误] 未安装 httpx"

    url = f"{OCR_SERVICE_URL.rstrip('/')}/ocr"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                url,
                json={"file_path": file_path, "max_pages": max_pages},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "[空] OCR 服务返回为空")
    except httpx.ConnectError:
        return (
            f"[错误] 无法连接 OCR 服务 ({OCR_SERVICE_URL})\n"
            f"请先启动: python ocr_server.py --port 5000"
        )
    except httpx.TimeoutException:
        return "[错误] OCR 服务超时"
    except Exception as e:
        return f"[OCR HTTP 错误] {e}"


# ============ PDF 直接提取文字 ============

def extract_text_from_pdf_direct(pdf_path: str, max_pages: int = 2) -> str:
    """
    直接从 PDF 中提取文字（适用于 Word 导出的文字型 PDF）
    默认只读前 max_pages 页
    返回提取的文字内容
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_to_read = min(max_pages, total_pages)

    texts = []
    for i in range(pages_to_read):
        page = doc[i]
        text = page.get_text().strip()
        if text:
            texts.append(f"--- 第 {i+1} 页 ---\n{text}")

    doc.close()
    return "\n\n".join(texts)


# ============ PDF 渲染后 OCR ============

def pdf_to_images(pdf_path: str, max_pages: int = 2, dpi: int = 300) -> list[bytes]:
    """将 PDF 的前 N 页渲染为图片"""
    images: list[bytes] = []
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_to_read = min(max_pages, total_pages)

    for i in range(pages_to_read):
        page = doc[i]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))

    doc.close()
    return images


def ocr_image_bytes(img_bytes: bytes) -> str:
    """对单张图片进行 OCR 识别"""
    ocr = get_ocr()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name
    try:
        result = ocr.ocr(tmp_path, cls=True)
        return _format_ocr_result(result)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _format_ocr_result(result: list) -> str:
    lines = []
    if result is None:
        return ""
    for page_result in result:
        if page_result is None:
            continue
        for line in page_result:
            text = line[1][0] if len(line) > 1 and line[1] else ""
            text = text.strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def ocr_pdf(pdf_path: str, max_pages: int = 2) -> str:
    """对 PDF 进行 OCR（前 N 页）"""
    # HTTP 模式 → 调远程服务
    if OCR_MODE == "http":
        return _ocr_via_http(pdf_path, max_pages)

    # 本地模式
    texts = []
    images = pdf_to_images(pdf_path, max_pages=max_pages)
    for i, img in enumerate(images):
        text = ocr_image_bytes(img)
        if text.strip():
            texts.append(f"--- 第 {i+1} 页 ---\n{text}")
    return "\n\n".join(texts) if texts else "[空] 未识别到文字内容"


def ocr_image(file_path: str) -> str:
    """对图片进行 OCR"""
    # HTTP 模式 → 调远程服务
    if OCR_MODE == "http":
        return _ocr_via_http(file_path, max_pages=1)

    # 本地模式
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    text = ocr_image_bytes(img_bytes)
    return text if text.strip() else "[空] 未识别到文字内容"


# ============ Word 文档提取 ============

def extract_text_from_docx(file_path: str, max_pages: int = 2) -> str:
    """
    从 .docx 文件中提取文字
    max_pages — 粗略控制（按段落数估算，因为 docx 没有明确页数概念）
    """
    try:
        from docx import Document
    except ImportError:
        return "[跳过] 未安装 python-docx 库"

    doc = Document(file_path)
    paragraphs = doc.paragraphs

    # 粗略估算：一般一页约 20-30 个段落
    est_paragraphs_per_page = 25
    max_paragraphs = max(3, max_pages * est_paragraphs_per_page)

    texts = []
    for i, para in enumerate(paragraphs):
        if i >= max_paragraphs:
            texts.append("... (已截断，仅显示前若干段落)")
            break
        text = para.text.strip()
        if text:
            texts.append(text)

    return "\n".join(texts) if texts else "[空] 未提取到文字"


# ============ 对外统一接口 ============

def extract_text(file_path: str, max_pages: int = 2) -> str:
    """
    智能提取文件文字 — 主入口

    策略:
    1. PDF → 先直接提取文字 → 够用直接返回
               → 不够用（扫描件）→ OCR 前 N 页
    2. Word (.docx) → python-docx 提取
    3. 图片 (.png/.jpg/.bmp) → OCR
    4. 其他格式 → 返回提示

    Args:
        file_path: 文件路径
        max_pages: 最大读取页数，默认 2 页

    Returns:
        提取到的文字内容
    """
    path = Path(file_path)
    if not path.exists():
        return f"[错误] 文件不存在: {file_path}"

    suffix = path.suffix.lower()

    # ---- PDF ----
    if suffix == ".pdf":
        # 先试着直接提取文字
        direct_text = extract_text_from_pdf_direct(str(path), max_pages=max_pages)
        clean_text = direct_text.strip()

        # 如果直接提取到的文字太少，判定为扫描件 → OCR
        if len(clean_text) < OCR_THRESHOLD:
            return ocr_pdf(str(path), max_pages=max_pages)
        return direct_text

    # ---- Word ----
    if suffix == ".docx":
        return extract_text_from_docx(str(path), max_pages=max_pages)

    # ---- 图片 ----
    if suffix in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"):
        return ocr_image(str(path))

    # ---- 文本文件 ----
    if suffix in (".txt", ".csv", ".md"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(5000)  # 最多前 5000 字符
        return content if content.strip() else "[空] 文件内容为空"

    return f"[跳过] 不支持的文件格式: {suffix}"
