"""
LLM 工具模块 — 统一调用大语言模型
支持 OpenAI 兼容接口 和 DashScope（通义千问）
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# ---------- 配置读取 ----------

def get_llm_config() -> dict:
    """
    从环境变量读取 LLM 配置
    优先级: OPENAI_API_KEY > DASHSCOPE_API_KEY
    
    .env 文件示例:
        # 方式一：OpenAI 兼容接口
        OPENAI_API_KEY=sk-xxx
        OPENAI_BASE_URL=https://api.openai.com/v1
        LLM_MODEL=gpt-4o-mini
        
        # 方式二：DashScope (通义千问)
        # DASHSCOPE_API_KEY=sk-xxx
        # LLM_MODEL=qwen-plus
    """
    config = {
        "api_key": os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "provider": "openai" if os.getenv("OPENAI_API_KEY") else "dashscope",
    }
    
    # 如果使用 DashScope 但没有设置 base_url，自动适配
    if os.getenv("DASHSCOPE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        config["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        config["provider"] = "dashscope"
        if not os.getenv("LLM_MODEL"):
            config["model"] = "qwen-plus"
    
    return config


# ---------- LLM 调用 ----------

def chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> str:
    """
    调用 LLM 进行对话
    返回模型回复的文本内容
    """
    from openai import OpenAI
    
    config = get_llm_config()
    
    if not config["api_key"]:
        raise ValueError(
            "未找到 API Key！请在项目根目录创建 .env 文件，设置:\n"
            "  OPENAI_API_KEY=sk-xxx\n"
            "  或\n"
            "  DASHSCOPE_API_KEY=sk-xxx"
        )
    
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    
    response = client.chat.completions.create(
        model=config["model"],
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    
    return response.choices[0].message.content or ""


def extract_structured(
    text: str,
    template_fields: list[str],
    project_type: str,
) -> dict:
    """
    将 OCR 识别出的文本，按模板字段提取为结构化 JSON
    
    Args:
        text: OCR 识别出的原始文本
        template_fields: 模板定义的字段列表（必填+选填）
        project_type: 项目类型名称
        
    Returns:
        dict: 提取结果，字段名 → 值
    """
    fields_str = "\n".join(f"  - {f}" for f in template_fields)
    
    system_prompt = """你是一个专业的工程文档信息提取助手。
你的任务是从项目文档的文本内容中，提取指定的结构化信息。

规则：
1. 仔细阅读文本，找到与目标字段相关的信息
2. 如果文本中明确提到了某个字段的值，直接提取
3. 如果文本中没有提到，该字段留空字符串 ""
4. 时间统一格式为 YYYY-MM-DD
5. 金额保留数字和单位（如 "125.8万元"）
6. 长度保留数字和单位（如 "1250米"）
7. 只输出 JSON，不要多余的解释"""

    user_prompt = f"""请从以下文本中提取 {project_type} 项目的相关信息。

需要提取的字段：
{fields_str}

文本内容：
---
{text[:10000]}  # 截取前 10000 字符避免超长
---

请严格按照 JSON 格式返回，例如：
{{"项目名称": "xxx", "开始时间": "2024-01-01", ...}}"""

    result = chat(system_prompt, user_prompt)
    
    # 尝试从回复中提取 JSON
    import json
    import re
    
    # 先找 ```json ... ``` 块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", result)
    if json_match:
        result = json_match.group(1).strip()
    
    # 再找 {...} 对象
    brace_match = re.search(r"\{[\s\S]*\}", result)
    if brace_match:
        result = brace_match.group(0)
    
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        # 如果解析失败，原样返回
        return {"_raw_llm_response": result, "_parse_error": "JSON 解析失败"}
