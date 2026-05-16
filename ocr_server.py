"""
OCR HTTP 常驻服务

把 PaddleOCR 作为一个 HTTP 服务长期运行，避免每次调用都重新加载模型。
模型只在启动时加载一次，后续请求直接使用。

启动:
  python ocr_server.py --port 5000

然后在 .env 中设置:
  OCR_MODE=http
  OCR_SERVICE_URL=http://localhost:5000

调用示例:
  curl -X POST http://localhost:5000/ocr \
    -H "Content-Type: application/json" \
    -d '{"file_path": "D:/project/合同.pdf", "max_pages": 2}'
"""

import argparse
import os
import sys
from pathlib import Path

# 保证能找到 core 模块
_project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root))

from core.ocr_cache import get_cache


# ----- FastAPI 应用 -----
try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("需要安装 FastAPI 和 Uvicorn：pip install fastapi uvicorn")
    sys.exit(1)

app = FastAPI(title="OCR 服务", version="1.0.0")

# 全局 OCR 实例（启动时初始化）
_ocr_instance = None


class OCRRequest(BaseModel):
    file_path: str
    max_pages: int = 2


class OCRResponse(BaseModel):
    text: str
    method: str  # "direct" | "ocr"
    pages: int
    cached: bool = False


@app.on_event("startup")
async def startup():
    """启动时加载 PaddleOCR（只加载一次）"""
    global _ocr_instance
    print("⏳ 正在加载 PaddleOCR 模型（首次加载约 5-15 秒）...")
    try:
        from core.extractor import _get_ocr
        _ocr_instance = _get_ocr()
        print("✅ PaddleOCR 模型加载完成")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        _ocr_instance = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ocr_loaded": _ocr_instance is not None,
    }


@app.post("/ocr", response_model=OCRResponse)
async def ocr(req: OCRRequest):
    """对文件进行文字提取（优先直接提取，不够再 OCR）"""
    file_path = req.file_path
    max_pages = req.max_pages

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    # 先查缓存
    cache = get_cache()
    cached_text = cache.get(file_path)
    if cached_text is not None:
        return OCRResponse(
            text=cached_text,
            method="cached",
            pages=max_pages,
            cached=True,
        )

    # 执行提取
    try:
        from core.extractor import extract_text
        text = extract_text(file_path, max_pages=max_pages)

        # 判断用了什么方法（粗略判断）
        method = "ocr" if "[空]" in text and "--- 第" in text else "direct"

        # 写入缓存
        cache.set(file_path, text, method=method)

        return OCRResponse(
            text=text,
            method=method,
            pages=max_pages,
            cached=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cache/stats")
async def cache_stats():
    """查看缓存统计"""
    cache = get_cache()
    return cache.stats()


@app.post("/cache/clear")
async def cache_clear(file_path: str | None = None):
    """清除缓存"""
    cache = get_cache()
    count = cache.clear(file_path)
    return {"cleared": count}


def main():
    parser = argparse.ArgumentParser(description="OCR HTTP 常驻服务")
    parser.add_argument("--port", "-p", type=int, default=5000, help="监听端口（默认 5000）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    args = parser.parse_args()

    print(f"🔌 OCR 服务启动: http://{args.host}:{args.port}")
    print(f"   POST /ocr    — 文字提取")
    print(f"   GET  /health — 健康检查")
    print(f"   GET  /cache/stats  — 缓存统计")
    print("按 Ctrl+C 停止")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
