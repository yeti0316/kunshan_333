import json
with open('多源项目信息提取器/output/工业企业整治结果.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for r in data:
    print('='*50)
    print(f"项目: {r['_folder']}")
    print(f"类型: {r['_type']}")
    print(f"提取结果:")
    for k,v in r.get('提取结果', {}).items():
        print(f"  {k}: {v}")
    print(f"验证:")
    for k,v in r.get('验证', {}).items():
        if isinstance(v, dict):
            files = [p.split('\\')[-1] for p in v.get('found_in',[])]
            print(f"  {k}: verified={v.get('verified')} in={files}")
    conf = r.get('置信度评估', {})
    print(f"置信度: {conf.get('等级')} 复核={conf.get('需人工复核')} 验证通过{conf.get('已验证字段数')}/{conf.get('已验证字段数',0)+conf.get('未找到原文字段数',0)}")
    print()
