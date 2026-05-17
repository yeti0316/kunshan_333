"""
系统提示词 — 只给工具和目标，不给具体步骤
核心约束：宁缺勿编，找不到明确证据就留空
"""

def build_system_prompt(project_type: str, template: dict) -> str:
    required = template.get("必填", [])
    optional = template.get("选填", [])

    req_fields_str = "\n".join(f"  - {f}" for f in required)
    opt_fields_str = "\n".join(f"  - {f}" for f in optional) if optional else "  （无）"

    hints = _build_hints(project_type, template)

    return f"""你是一个工程文档信息提取助手。按 ReAct 模式工作。

【可用工具】
- list_files(path): 列出文件夹下所有文件
- read_document(path, pages=2): 读取文档文字（PDF/Word/图片均可）

【当前任务】
项目类型：{project_type}

必填字段：
{req_fields_str}

选填字段：
{opt_fields_str}
{hints}
【提取规则】

1. 宁缺勿编 — 这是最重要的原则。
   - 只有在文档里能**找到明确的、对应的原文**，才填写该字段。
   - 找不到 → 留空字符串 ""
   - 不确定 → 留空 ""
   - 隐约感觉有 → 留空 ""
   - 宁可让字段空着交给人工复核，也不要填一个你没把握的值。

2. 什么是「明确证据」？
   - 文档里写「项目名称：新华路管网检测」→ 项目名称 可填
   - 文档里写「合同金额：856000元」→ 合同金额 可填
   - 文档里只写了「该工程」三个字 → 不能推断它就是任何特定项目名称
   - 文档里提到了「人民路」但没有说它是检测道路 → 不能填到检测道路
   - 文档里有数字但没有单位 → 不要自己加单位

3. 如果一个必填字段找不到 → 读其他文件。所有文件读完还找不到 → 留空。

4. 输出格式（只输出 JSON，不要多余文字）：

```json
{{{{
  "提取结果": {{{{
    "项目名称": "新华路管网检测修复工程",
    "开始时间": "2024-03-15",
    "合同金额": "85.6万元",
    ...
  }}}},
  "已读文件": ["合同.txt", "中标通知书.txt"]
}}}}```

已读文件列表请如实列出你调用 read_document 读过的每个文件名（相对路径或文件名即可）。"""


def _build_hints(project_type: str, template: dict) -> str:
    common_files = template.get("常见文件", [])
    hints = []

    hints.append("经验提示（参考，最终以文档原文为准）：")
    hints.append("- 合同 → 通常有项目名称、金额、工期")
    hints.append("- 中标通知书 → 通常有项目名称和日期")
    hints.append("- 检测/施工报告 → 通常有管道长度和道路名称")

    if common_files:
        hints.append(f"- 该项目类型常见文件：{'、'.join(common_files)}，可优先查看")

    hints.append("- 文件内容如果是宣传册/名片/不相干的内容，跳过它")

    return "\n".join(hints) + "\n"


def build_project_prompt(project_path: str, project_type: str) -> str:
    return (
        f"项目文件夹：{project_path}\n"
        f"项目类型：{project_type}\n\n"
        f"请读取文件并提取字段。找不到明确证据的字段留空。"
    )
