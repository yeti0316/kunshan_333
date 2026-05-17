"""
ReAct Agent 执行器
每个项目启动一个独立 Agent，系统提示词中已嵌入模板信息
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from core.llm_utils import get_llm_config
from core.template_loader import load_templates, get_all_field_names
from core.verify import verify_extraction
from core.ocr_cache import get_cache
from agent.tools import list_project_files, read_document
from agent.prompts import build_system_prompt, build_project_prompt


def _get_llm():
    """从环境变量创建 LLM 实例"""
    config = get_llm_config()
    return ChatOpenAI(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=0.1,
    )


def _try_parse_json(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON"""
    if not text:
        return None

    # 找 ```json ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        candidate = json_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 找 {...} 最外层花括号
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


def process_project(
    project_path: str,
    project_type: str,
    template: dict | None = None,
) -> dict[str, Any]:
    """
    使用 ReAct Agent 处理一个项目

    Args:
        project_path: 项目文件夹路径
        project_type: 项目类型（如"管网检测修复"）
        template: 可选，直接传入模板。不传则按类型自动加载。

    Returns:
        { folder, type, status, result, error, files_processed }
    """
    path = Path(project_path)
    folder_name = path.name

    if not path.exists():
        return {"folder": folder_name, "type": project_type,
                "status": "error", "error": "路径不存在", "result": {}}
    if not path.is_dir():
        return {"folder": folder_name, "type": project_type,
                "status": "error", "error": "不是文件夹", "result": {}}

    # 加载模板
    if template is None:
        templates = load_templates()
        matched = [t for t in templates if t.get("类型") == project_type]
        template = matched[0] if matched else {
            "类型": project_type,
            "必填": ["项目名称", "开始时间", "完成时间", "合同金额"],
            "选填": [],
        }

    # 构建提示词
    system_prompt = build_system_prompt(project_type, template)
    user_message = build_project_prompt(str(path), project_type)

    # 创建 ReAct Agent
    llm = _get_llm()
    tools = [list_project_files, read_document]

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=system_prompt),
        checkpointer=MemorySaver(),
    )

    thread_id = f"project_{folder_name}_{os.urandom(4).hex()}"

    try:
        final_state = agent.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"configurable": {"thread_id": thread_id}},
        )

        messages = final_state.get("messages", [])

        # 统计调用次数
        tool_calls = sum(
            1 for m in messages
            if hasattr(m, 'tool_calls') and m.tool_calls
        )

        # 解析最终结果
        last_msg = messages[-1] if messages else None
        result_text = last_msg.content if last_msg else ""
        result_json = _try_parse_json(result_text)

        # 如果没解析出 JSON，把所有 LLM 消息拼接起来再试一次
        if not result_json:
            full_text = "\n".join(
                m.content for m in messages
                if hasattr(m, 'content') and m.content
            )
            result_json = _try_parse_json(full_text)

        # 记录处理过的文件
        processed = _extract_processed_files(messages)

        # 拿到结果体（Agent 可能输出 {"提取结果": {...}, "已读文件": [...]} 或直接 {...}）
        raw_result = result_json if result_json else {"_raw": result_text}
        extracted_fields = raw_result.get("提取结果", raw_result)

        # ===== 事后验证：拿提取值去 OCR 原文里核对 =====
        cache = get_cache()
        doc_texts = {}
        for fpath in processed:
            text = cache.get(fpath)
            if text:
                doc_texts[fpath] = text

        # 如果缓存没有（可能是 HTTP OCR 模式），从 agent 消息中提取工具返回的原文
        if not doc_texts:
            doc_texts = _extract_tool_results(messages)

        verified_result = verify_extraction(extracted_fields, doc_texts)

        return {
            "folder": folder_name,
            "type": project_type,
            "status": "complete",
            "result": verified_result,
            "tool_calls": tool_calls,
            "files_processed": processed,
        }

    except Exception as e:
        return {
            "folder": folder_name,
            "type": project_type,
            "status": "error",
            "error": str(e),
            "result": {},
            "files_processed": [],
        }


def batch_process_parallel(
    projects: list[dict],
    template_map: dict[str, dict],
    *,
    max_workers: int = 3,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """
    多线程并行处理多个项目

    Args:
        projects: 项目列表，每项含 path 和 type
        template_map: 模板字典 {类型: template}
        max_workers: 同时处理的最大项目数（默认 3）
        verbose: 是否打印进度

    Returns:
        结果列表
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import time

    print_lock = threading.Lock()
    results: list[dict[str, Any]] = []
    completed = 0
    errors = 0
    start_time = time.time()

    def worker(project: dict) -> dict[str, Any]:
        nonlocal completed, errors
        proj_path = project["path"]
        proj_type = project["type"]
        folder_name = Path(proj_path).name

        template = template_map.get(proj_type) or {
            "类型": proj_type,
            "必填": ["项目名称", "开始时间", "完成时间", "合同金额"],
            "选填": [],
        }

        t0 = time.time()
        result = process_project(proj_path, proj_type, template)
        elapsed = time.time() - t0

        if verbose:
            with print_lock:
                status_icon = "✓" if result["status"] == "complete" else "✗"
                field_count = len(
                    [k for k in result.get("result", {}) if not k.startswith("_")]
                )
                print(f"  {status_icon} {folder_name}  "
                      f"({proj_type})  {elapsed:.0f}s  "
                      f"{field_count}字段  "
                      f"{result.get('tool_calls', 0)}次调用")

        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, p): p for p in projects}

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                if result["status"] == "complete":
                    completed += 1
                else:
                    errors += 1
            except Exception as e:
                p = futures[future]
                errors += 1
                results.append({
                    "folder": Path(p["path"]).name,
                    "type": p["type"],
                    "status": "error",
                    "error": str(e),
                    "result": {},
                })
                if verbose:
                    with print_lock:
                        print(f"  ✗ {Path(p['path']).name}  异常: {e}")

    elapsed = time.time() - start_time
    if verbose:
        print(f"\n  ⏱ 总耗时: {elapsed:.0f}s  (并发 {max_workers} 线程)")
        print(f"  ✓ {completed} 成功  ✗ {errors} 失败")

    return results


def _extract_processed_files(messages: list) -> list[str]:
    """从消息历史中提取被 read_document 处理过的文件"""
    files = []
    for m in messages:
        if hasattr(m, 'tool_calls') and m.tool_calls:
            for tc in m.tool_calls:
                if tc.get("name") == "read_document":
                    args = tc.get("args", {})
                    fpath = args.get("file_path", "")
                    if fpath:
                        files.append(fpath)
    return list(set(files))


def _extract_tool_results(messages: list) -> dict[str, str]:
    """
    从消息历史中提取工具调用的返回内容 {文件路径: 文字}
    当缓存不可用时作为后备
    """
    results = {}
    # 找 ToolMessage，它们包含工具返回的内容
    for m in messages:
        if hasattr(m, 'name') and m.name == "read_document":
            content = m.content if hasattr(m, 'content') else ""
            # 尝试从 ToolMessage 中推断文件路径
            # （LangGraph 的 ToolMessage 不直接暴露参数，用内容推测）
            pass

    # 更可靠的方式：从 AI 消息的 tool_calls 中找参数，
    # 从后续的 Tool 消息中找结果（它们按调用顺序配对）
    tool_messages = [m for m in messages if hasattr(m, 'name') and m.name == "read_document"]
    tool_call_msgs = []
    for m in messages:
        if hasattr(m, 'tool_calls') and m.tool_calls:
            for tc in m.tool_calls:
                if tc.get("name") == "read_document":
                    tool_call_msgs.append(tc)

    # 配对
    for i, tc in enumerate(tool_call_msgs):
        fpath = tc.get("args", {}).get("file_path", "")
        content = tool_messages[i].content if i < len(tool_messages) else ""
        if fpath and content:
            results[fpath] = content

    return results
