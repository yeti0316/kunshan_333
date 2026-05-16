"""
OCR 缓存模块 — 已提取的文字存为 JSON 缓存，避免重复 OCR

缓存策略：
- 每个源文件一个独立缓存文件，存在 cache/ocr/ 目录下
- 缓存 key = 文件绝对路径的 hash
- 同时记录文件的修改时间 (mtime)，文件变了就重新提取
- 线程安全：每个缓存文件独立读写，无竞争
"""

import hashlib
import json
import os
import time
from pathlib import Path


class OCRCache:
    """OCR 结果缓存"""

    def __init__(self, cache_dir: str | None = None):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent / "cache" / "ocr"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, file_path: str) -> Path:
        """根据文件路径生成缓存文件路径"""
        abs_path = str(Path(file_path).resolve())
        h = hashlib.md5(abs_path.encode("utf-8")).hexdigest()
        # 保留原文件名便于调试
        fname = Path(file_path).name
        # 限制文件名长度
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)[:60]
        return self.cache_dir / f"{h}_{safe_name}.json"

    def get(self, file_path: str) -> str | None:
        """
        获取缓存中的文字内容
        如果文件已被修改（mtime 变了），返回 None
        """
        cache_file = self._cache_path(file_path)
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        # 检查文件是否被修改过
        current_mtime = os.path.getmtime(file_path)
        if data.get("mtime") != current_mtime:
            return None

        return data.get("text")

    def set(self, file_path: str, text: str, method: str = "direct") -> None:
        """保存提取结果到缓存"""
        cache_file = self._cache_path(file_path)
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = 0

        data = {
            "file_path": str(Path(file_path).resolve()),
            "mtime": mtime,
            "text": text,
            "method": method,  # "direct" | "ocr"
            "cached_at": time.time(),
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear(self, file_path: str | None = None) -> int:
        """
        清除缓存
        - 指定文件 → 只清除该文件
        - None → 清除所有缓存
        返回清除的文件数
        """
        if file_path:
            cache_file = self._cache_path(file_path)
            if cache_file.exists():
                cache_file.unlink()
                return 1
            return 0

        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

    def stats(self) -> dict:
        """缓存统计"""
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "cache_dir": str(self.cache_dir),
            "cached_files": len(files),
            "total_size_kb": total_size // 1024,
        }


# 全局单例
_global_cache: OCRCache | None = None


def get_cache() -> OCRCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = OCRCache()
    return _global_cache
