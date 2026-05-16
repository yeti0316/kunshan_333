"""
系统提示词 — 只给工具和目标，不给具体步骤
让 Agent 自己 ReAct 思考该怎么做
"""

def build_system_prompt(project_type: str, template: dict) -> str:
    """
    构建系统提示词

    核心原则：告诉 Agent 有什么工具、要达成什么目标、有什么约束
    具体怎么做 → 让它自己推理
    """
    required = template.get("必填", [])
    optional = template.get("选填", [])

    # 字段列表
    req_fields = "\n".join(f"  - {f}" for f in required)
    opt_fields = "\n".join(f"  - {f}" for f in optional) if optional else "  （无）"

    return f"""你是一个工程文档信息提取助手。按 ReAct 模式工作。

【可用工具】
- list_files(path): 列出文件夹下所有文件
- read_document(path, pages=2): 读取文档文字（PDF/Word/图片均可，自动选择直接提取或OCR）

【当前任务】
项目类型：{project_type}
需要从文档中提取以下信息：

必填字段：
{req_fields}

选填字段：
{opt_fields}

【规则】
- 时间格式 YYYY-MM-DD
- 金额保留数字+单位，如"125.8万元"
- 长度保留数字+单位，如"1250米"
- 只从文档原文中提取，不要编造
- 所有能读的文件都读完了还缺字段 → 用已有的输出，不要硬填
- 最终只输出 JSON，不要多余的文字"""


def build_project_prompt(project_path: str, project_type: str) -> str:
    """初始用户消息 — 仅交代背景，不说怎么做"""
    return (
        f"项目文件夹：{project_path}\n"
        f"项目类型：{project_type}\n\n"
        f"请提取所有必填和选填字段。"
    )
