# 多源项目信息提取器

基于 **LangGraph ReAct Agent** 的工程文档信息提取工具。

## 适用场景

- 📁 有大量项目文件夹（几千上万个），每个文件夹内含若干文档
- 📄 文档格式杂乱（文字PDF / 扫描件PDF / Word / 图片混在一起）
- 🎯 **项目类型和路径已在一份 Excel 清单中登记好**
- 🔍 需要从每份文档中提取关键信息（项目名、时间、金额、长度等）
- 📊 汇总为结构化 Excel，方便做统计分析

## 工作流程

```
你有一份项目清单.xlsx
├── 项目A  |  管网检测修复  |  D:\projects\A
├── 项目B  |  农村污水整治  |  D:\projects\B
└── 项目C  |  管网新建      |  D:\projects\C
        │
        ▼
程序逐一处理每个项目：
  ① 根据「项目类型」从 templates.yaml 加载对应模板
  ② 把模板字段直接告诉 Agent（不用它猜）
  ③ Agent 自主决定读哪些文件、怎么读
  ④ 输出结构化 JSON
        │
        ▼
汇总 → 结果.xlsx（每个项目一行，字段为一列）
```

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

### 2. 从 Excel 清单运行

```bash
conda activate rag
python run.py --input 项目清单.xlsx --output 结果.xlsx
```

Excel 清单需要至少两列：**项目路径** 和 **项目类型**

### 3. 或直接扫描目录

```bash
python run.py --root D:\projects --output 结果.xlsx
```

### 4. 先看看有多少项目

```bash
python run.py --root D:\projects --dry-run
```

## Agent 的工作方式（真正的 ReAct）

每个项目启动一个独立的 ReAct Agent，它只有 **2 个工具**：

| 工具 | 功能 |
|------|------|
| `list_files(path)` | 列出文件夹下的文件 |
| `read_document(path, pages=2)` | 智能读取文档文字 |

Agent 拿到提示词时已经知道了：
- ✅ 项目类型是什么
- ✅ 要提取哪些字段（必填/选填）
- ✅ 文件夹路径

然后它自主决定：先看有什么文件 → 读哪个最可能有用 → 提取信息 → 还缺什么 → 再读另一个…

### 智能读取策略

| 情况 | 处理方式 |
|------|---------|
| Word 生成的文字 PDF | 直接提取文字，**不走 OCR** |
| 扫描仪生成的图片 PDF | 自动识别 → **走 OCR** |
| Word 文档 (.docx) | 直接解析 |
| 只读前 2 页 | 关键信息（项目名、金额、日期）全在前几页 |

## 自定义模板

编辑 `config/templates.yaml`：

```yaml
  - 类型: 管网检测修复
    必填:
      - 项目名称
      - 开始时间
      - 合同金额
      - 检测道路
    选填:
      - 雨水管长度(米)
      - 污水管长度(米)
    常见文件: [中标通知书, 合同, 检测报告]
```

## 项目结构

```
多源项目信息提取器/
├── run.py                  ← 命令行入口（用这个）
├── agent/
│   ├── tools.py            ← 2 个工具：list_files, read_document
│   ├── prompts.py          ← 动态构建系统提示词（模板嵌入其中）
│   └── runner.py           ← ReAct Agent 执行器
├── core/
│   ├── extractor.py        ← 智能文字提取（核心）
│   ├── llm_utils.py        ← LLM 调用
│   ├── excel_reader.py     ← 读取项目清单 Excel
│   ├── excel_utils.py      ← 导出结果 Excel
│   └── template_loader.py  ← 加载模板
├── config/
│   └── templates.yaml      ← 项目类型模板（你来维护）
├── output/                 ← 输出目录
├── .env.example
├── .gitignore
└── pyproject.toml
```
