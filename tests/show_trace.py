import json
with open('多源项目信息提取器/output/工业企业整治结果_v5.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for r in data:
    print('='*60)
    print(f"项目: {r['_folder']}")
    print(f"类型: {r['_type']}")
    print()

    trace = r.get('_reasoning_trace', [])
    if trace:
        print("🧠 推理过程:")
        for step in trace:
            step_type = step.get("类型", "")
            print(f"  [{step['步骤']}] {step_type}")
            if step_type == "🔧 调用工具":
                print(f"       工具: {step['工具']}({step['参数']})")
            elif step_type == "📋 工具返回":
                print(f"       返回: {step['内容摘要'][:200]}")
            elif step_type == "💭 Agent思考":
                print(f"       {step['内容'][:250]}")
            print()

    result = r.get('提取结果', {})
    print("📊 最终提取:")
    for k, v in result.items():
        print(f"  {k}: {v}")
