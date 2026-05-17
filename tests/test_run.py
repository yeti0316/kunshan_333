"""
快速测试脚本 — 用测试数据验证 Agent 是否正常工作

用法（在项目根目录执行）:
  python tests/test_run.py
"""

import sys
from pathlib import Path

# 确保能找到核心模块
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from agent.runner import process_project, batch_process_parallel
from core.template_loader import load_templates


def main():
    # 加载模板
    templates = load_templates()
    template_map = {t["类型"]: t for t in templates}
    print(f"已加载 {len(templates)} 个模板\n")

    # 测试项目 1：管网检测修复
    print("=" * 50)
    print("测试 1：新华路管网检测（管网检测修复）")
    print("=" * 50)

    result = process_project(
        "tests/test_projects/新华路管网检测",
        "管网检测修复",
        template_map.get("管网检测修复"),
    )

    print(f"\n状态: {result['status']}")
    print(f"提取结果:")
    for k, v in result.get("result", {}).items():
        print(f"  {k}: {v}")
    print(f"工具调用次数: {result.get('tool_calls', 0)}")

    # 测试项目 2：农村污水整治
    print("\n" + "=" * 50)
    print("测试 2：张浦镇农污整治（农村污水整治）")
    print("=" * 50)

    result2 = process_project(
        "tests/test_projects/张浦镇农污整治",
        "农村污水整治",
        template_map.get("农村污水整治"),
    )

    print(f"\n状态: {result2['status']}")
    print(f"提取结果:")
    for k, v in result2.get("result", {}).items():
        print(f"  {k}: {v}")
    print(f"工具调用次数: {result2.get('tool_calls', 0)}")


if __name__ == "__main__":
    main()
