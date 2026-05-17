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
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
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


# ============ 文件上传接口 ============

@app.post("/ocr/upload")
async def ocr_upload(file: UploadFile = File(...), max_pages: int = Form(2)):
    """
    上传文件进行 OCR（支持 PDF / 图片 / Word）
    文件保存到临时目录后调用 extract_text
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    # 写入临时文件
    import shutil
    import tempfile

    suffix = Path(file.filename or "unknown").suffix or ".tmp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        from core.extractor import extract_text

        # 先查缓存
        cache = get_cache()
        cached_text = cache.get(tmp_path)
        if cached_text is not None:
            method = "cached"
            text = cached_text
            cached = True
        else:
            text = extract_text(tmp_path, max_pages=max_pages)
            if "[空]" in text and "--- 第" in text or text.startswith("[OCR"):
                method = "ocr"
            else:
                method = "direct"
            cache.set(tmp_path, text, method=method)
            cached = False

        return {
            "success": True,
            "file_name": file.filename,
            "text": text,
            "method": method,
            "pages": max_pages,
            "cached": cached,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ============ Web 页面 ============

@app.get("/ui", response_class=HTMLResponse)
async def web_ui():
    """简单的 Web 上传页面"""
    return HTMLResponse(content=UI_HTML)


UI_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OCR 文字提取</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
            background: #f0f2f5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 { font-size: 24px; color: #1a1a2e; }
        .header p { color: #666; margin-top: 8px; font-size: 14px; }
        .upload-zone {
            width: 100%;
            max-width: 560px;
            background: #fff;
            border: 2px dashed #c0c4cc;
            border-radius: 12px;
            padding: 48px 24px;
            text-align: center;
            cursor: pointer;
            transition: all .2s;
        }
        .upload-zone:hover, .upload-zone.dragover {
            border-color: #409eff;
            background: #ecf5ff;
        }
        .upload-zone .icon { font-size: 48px; margin-bottom: 12px; }
        .upload-zone .hint { color: #909399; font-size: 14px; }
        .upload-zone input[type=file] { display: none; }
        .settings {
            margin-top: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            justify-content: center;
            color: #666;
            font-size: 14px;
        }
        .settings input {
            width: 60px;
            padding: 4px 8px;
            border: 1px solid #dcdfe6;
            border-radius: 4px;
            text-align: center;
        }
        .status {
            margin-top: 16px;
            color: #409eff;
            font-size: 14px;
            min-height: 20px;
        }
        .result {
            width: 100%;
            max-width: 700px;
            margin-top: 24px;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            overflow: hidden;
            display: none;
        }
        .result.show { display: block; }
        .result .meta {
            padding: 12px 16px;
            background: #fafafa;
            border-bottom: 1px solid #ebeef5;
            font-size: 13px;
            color: #666;
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }
        .result .meta span { white-space: nowrap; }
        .result .meta .method { color: #67c23a; font-weight: bold; }
        .result .meta .cached { color: #e6a23c; }
        .result pre {
            padding: 20px 24px;
            font-size: 15px;
            line-height: 1.7;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 500px;
            overflow-y: auto;
            font-family: "Microsoft YaHei", monospace;
        }
        .error {
            color: #f56c6c;
            background: #fef0f0;
            border: 1px solid #fde2e2;
            padding: 16px;
            border-radius: 8px;
            margin-top: 16px;
            display: none;
            max-width: 700px;
            width: 100%;
        }
        .error.show { display: block; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📄 OCR 文字提取</h1>
        <p>上传 PDF / 图片 / Word，自动识别文字 — 文字型 PDF 直接提取，扫描件走 OCR</p>
    </div>

    <div class="upload-zone" id="uploadZone">
        <div class="icon">📤</div>
        <div class="hint">点击选择文件，或拖拽文件到此处</div>
        <input type="file" id="fileInput" accept=".pdf,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.docx">
    </div>

    <div class="settings">
        <label>最大页数：</label>
        <input type="number" id="maxPages" value="2" min="1" max="20">
    </div>

    <div class="status" id="status"></div>

    <div class="error" id="error"></div>

    <div class="result" id="result">
        <div class="meta" id="meta"></div>
        <pre id="textContent"></pre>
    </div>

    <script>
        const zone = document.getElementById('uploadZone');
        const input = document.getElementById('fileInput');
        const status = document.getElementById('status');
        const result = document.getElementById('result');
        const meta = document.getElementById('meta');
        const textContent = document.getElementById('textContent');
        const errorDiv = document.getElementById('error');
        const maxPages = document.getElementById('maxPages');

        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', e => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                handleFile(e.dataTransfer.files[0]);
            }
        });
        input.addEventListener('change', () => {
            if (input.files.length) handleFile(input.files[0]);
        });

        async function handleFile(file) {
            result.classList.remove('show');
            errorDiv.classList.remove('show');
            status.textContent = '⏳ 正在提取文字...';

            const form = new FormData();
            form.append('file', file);
            form.append('max_pages', maxPages.value || 2);

            try {
                const resp = await fetch('/ocr/upload', { method: 'POST', body: form });
                const data = await resp.json();

                if (!resp.ok) {
                    throw new Error(data.detail || '未知错误');
                }

                status.textContent = '✅ 提取完成';
                meta.innerHTML =
                    '<span>📁 ' + data.file_name + '</span>' +
                    '<span class="method">🔬 ' + data.method + '</span>' +
                    '<span>📄 ' + data.pages + ' 页</span>' +
                    (data.cached ? '<span class="cached">💾 缓存命中</span>' : '');
                textContent.textContent = data.text || '（未识别到文字）';
                result.classList.add('show');
            } catch (err) {
                status.textContent = '';
                errorDiv.textContent = '❌ ' + err.message;
                errorDiv.classList.add('show');
            }
        }
    </script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="OCR HTTP 常驻服务")
    parser.add_argument("--port", "-p", type=int, default=5000, help="监听端口（默认 5000）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    args = parser.parse_args()

    print(f"🔌 OCR 服务启动: http://{args.host}:{args.port}")
    print(f"   🌐 Web 页面: http://{args.host}:{args.port}/ui")
    print(f"   POST /ocr         — 文字提取（传文件路径）")
    print(f"   POST /ocr/upload  — 文字提取（上传文件）")
    print(f"   GET  /health      — 健康检查")
    print(f"   GET  /cache/stats — 缓存统计")
    print("按 Ctrl+C 停止")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
