"""
断点续跑模块 — 记录每个项目的处理状态，支持中断后恢复

数据保存在 output/checkpoint.json 中：
  {
    "D:/projects/A": {
      "status": "complete",      # complete | partial | failed | skipped
      "confidence": "高",
      "fields_extracted": 10,
      "files_processed": ["合同.txt"],
      "updated_at": "2024-..."
    },
    "D:/projects/B": {
      "status": "failed",
      "error": "...",
      ...
    }
  }

续跑逻辑：
  - complete + 高置信度 → 跳过
  - complete + 中/低置信度 → 重新跑（会复用缓存中已读的文件）
  - partial/failed → 重新跑
  - 未在 checkpoint 中的 → 新项目，正常跑
"""

import json
import time
from pathlib import Path
from typing import Any


class Checkpoint:
    """断点续跑管理器"""

    def __init__(self, checkpoint_path: str | None = None):
        if checkpoint_path is None:
            checkpoint_path = Path(__file__).resolve().parent.parent / "output" / "checkpoint.json"
        self.path = Path(checkpoint_path)
        self.data: dict[str, dict] = {}
        self._load()

    def _load(self):
        """加载已有 checkpoint"""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def save(self):
        """保存 checkpoint"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, project_path: str) -> dict | None:
        """获取某项目的 checkpoint 记录"""
        path = str(Path(project_path).resolve())
        return self.data.get(path)

    def set(self, project_path: str, result: dict[str, Any]):
        """记录项目结果"""
        path = str(Path(project_path).resolve())
        confidence = result.get("result", {}).get("置信度评估", {}).get("等级", "?")
        self.data[path] = {
            "status": result.get("status", "error"),
            "confidence": confidence,
            "fields_extracted": len(result.get("result", {}).get("提取结果", {})),
            "files_processed": result.get("files_processed", []),
            "error": result.get("error"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()

    def should_skip(self, project_path: str) -> bool:
        """
        判断项目是否应该跳过

        规则：
        - complete + 高置信度 → 跳过
        - 其他情况 → 不跳过（重新跑）
        """
        record = self.get(project_path)
        if record is None:
            return False  # 没跑过
        status = record.get("status", "")
        confidence = record.get("confidence", "")
        return status == "complete" and confidence == "高"

    def stats(self) -> dict:
        """统计"""
        total = len(self.data)
        complete = sum(1 for r in self.data.values() if r.get("status") == "complete")
        high_conf = sum(1 for r in self.data.values() if r.get("confidence") == "高")
        failed = sum(1 for r in self.data.values() if r.get("status") in ("error", "failed"))
        return {
            "total_processed": total,
            "complete": complete,
            "high_confidence": high_conf,
            "failed": failed,
            "will_skip": sum(1 for k in self.data if self.should_skip(k)),
        }
