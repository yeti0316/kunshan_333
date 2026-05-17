"""
多源项目信息提取器 — 命令行入口

用法:
  # 从 Excel 清单读取项目列表（串行，默认）
  python run.py --input 项目清单.xlsx --output 结果.xlsx

  # 并发处理（几百个文件夹用这个提速）
  python run.py --input 项目清单.xlsx --output 结果.xlsx --workers 5

  # 直接扫目录
  python run.py --root D:\projects --output 结果.xlsx --workers 3

  # 先看看有多少项目，不实际跑
  python run.py --root D:\projects --dry-run

  # 限制处理数量
  python run.py --input 项目清单.xlsx --output 结果.xlsx --max 20 --workers 4
"""

import argparse
import json
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root))

from agent.runner import process_project, batch_process_parallel
from core.template_loader import load_templates
from core.excel_reader import read_project_list, read_directory_as_project_list
from core.excel_utils import results_to_excel
from core.checkpoint import Checkpoint


def main():
    parser = argparse.ArgumentParser(
        description="多源项目信息提取器 — 从项目文档中提取结构化信息",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py --input 项目清单.xlsx --output 结果.xlsx
  python run.py --root D:\\projects --output 结果.xlsx --workers 5
  python run.py --root D:\\projects --dry-run
        """,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input", "-i",
        help="项目清单 Excel 文件路径（需包含「项目路径」和「项目类型」列）",
    )
    input_group.add_argument(
        "--root", "-r",
        help="项目根目录（自动处理所有一级子文件夹，类型需从名称匹配）",
    )

    parser.add_argument("--output", "-o", default="output/结果.xlsx",
                        help="输出 Excel 文件路径（默认 output/结果.xlsx）")
    parser.add_argument("--max", "-m", type=int, default=None,
                        help="最多处理多少个项目")
    parser.add_argument("--workers", "-w", type=int, default=1,
                        help="并发线程数（默认 1=串行。几百个文件夹建议 3~5）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅列出项目清单，不执行提取")

    args = parser.parse_args()

    # ---- 读取项目清单 ----
    print("📋 读取项目清单...")
    if args.input:
        projects = read_project_list(args.input)
        source_desc = f"Excel: {args.input}"
    else:
        projects = read_directory_as_project_list(args.root)
        source_desc = f"目录: {args.root}"

    if args.max:
        projects = projects[:args.max]

    print(f"   共 {len(projects)} 个项目 ({source_desc})")

    if args.dry_run:
        print("\n项目清单：")
        for i, p in enumerate(projects, 1):
            print(f"  {i:3d}. [{p['type']}] {p['path']}")
        return

    # ---- 加载模板 ----
    templates = load_templates()
    template_map = {t["类型"]: t for t in templates}
    print(f"   已加载 {len(templates)} 个项目类型模板")
    if args.workers > 1:
        print(f"   ⚡ 并发 {args.workers} 线程")

    # ---- 断点续跑 ----
    checkpoint = Checkpoint()
    ckpt_stats = checkpoint.stats()
    if ckpt_stats["total_processed"] > 0:
        print(f"\n📌 断点续跑：已处理 {ckpt_stats['complete']} 个")
        print(f"   高置信度可跳过: {ckpt_stats['will_skip']} 个")
        print(f"   还需重新处理: {ckpt_stats['total_processed'] - ckpt_stats['will_skip']} 个")

    # 过滤：跳过已成功 + 高置信度的
    to_process = []
    skipped = 0
    for p in projects:
        if checkpoint.should_skip(p["path"]):
            skipped += 1
        else:
            to_process.append(p)

    if skipped:
        print(f"   ⏭ 跳过 {skipped} 个已完成项目")
    print(f"   本次处理: {len(to_process)} 个项目\n")

    projects = to_process
    if not projects:
        print("✅ 所有项目已完成，无需处理。")
        return

    # ---- 处理项目 ----
    overall_start = time.time()

    if args.workers > 1:
        # === 并行模式 ===
        print(f"\n🚀 开始处理（并行）...")
        raw_results = batch_process_parallel(
            projects,
            template_map,
            max_workers=args.workers,
            verbose=True,
        )
        results = []
        for r in raw_results:
            clean = r.get("result", {})
            if isinstance(clean, dict):
                clean["_folder"] = r["folder"]
                clean["_path"] = r.get("path", "")
                clean["_type"] = r["type"]
                clean["_status"] = r["status"]
                if r.get("error"):
                    clean["_error"] = r["error"]
            results.append(clean)
            # 保存 checkpoint
            checkpoint.set(r.get("path", ""), r)

    else:
        # === 串行模式 ===
        print(f"\n🚀 开始处理（串行）...")
        results = []
        for i, project in enumerate(projects, 1):
            proj_path = project["path"]
            proj_type = project["type"]
            folder_name = Path(proj_path).name

            template = template_map.get(proj_type) or {
                "类型": proj_type,
                "必填": ["项目名称", "开始时间", "完成时间", "合同金额"],
                "选填": [],
            }

            print(f"\n  [{i}/{len(projects)}] {folder_name} ({proj_type})")
            sys.stdout.flush()

            t0 = time.time()
            result = process_project(proj_path, proj_type, template)
            elapsed = time.time() - t0

            if result["status"] == "complete":
                field_count = len(
                    [k for k in result.get("result", {}) if not k.startswith("_")]
                )
                print(f"     ✓ {elapsed:.0f}s | {field_count} 字段 | "
                      f"{result.get('tool_calls', 0)} 次调用")
                if result.get("files_processed"):
                    for f in result["files_processed"]:
                        fn = Path(f).name
                        print(f"       📄 {fn}")
            else:
                print(f"     ✗ 失败: {result.get('error', '未知错误')}")

            clean = result.get("result", {})
            if isinstance(clean, dict):
                clean["_folder"] = folder_name
                clean["_path"] = proj_path
                clean["_type"] = proj_type
                clean["_status"] = result["status"]
                if result.get("error"):
                    clean["_error"] = result["error"]
            results.append(clean)

            # 保存 checkpoint
            checkpoint.set(proj_path, result)

    total_elapsed = time.time() - overall_start
    completed = sum(1 for r in results if r.get("_status") == "complete")
    errors = sum(1 for r in results if r.get("_status") == "error")

    print(f"\n{'='*50}")
    print(f"📊 处理完成：共 {len(results)} 个项目")
    print(f"   ✓ 成功: {completed}")
    print(f"   ✗ 失败: {errors}")
    print(f"   ⏱ 总耗时: {total_elapsed:.0f}s")
    if args.workers > 1:
        avg_per_project = total_elapsed / len(results) if results else 0
        print(f"   ⚡ 平均每个项目 {avg_per_project:.1f}s（并发 {args.workers} 线程）")

    # ---- 输出 ----
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = output_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📄 JSON: {json_path}")

    try:
        excel_path = results_to_excel(str(json_path), str(output_path))
        print(f"📊 Excel: {excel_path}")
    except Exception as e:
        print(f"⚠  Excel 导出失败: {e}")

    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
