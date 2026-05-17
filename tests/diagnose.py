import json
with open('多源项目信息提取器/output/工业企业整治结果.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

ok = [r for r in data if r.get('_status') == 'complete']
err = [r for r in data if r.get('_status') == 'error']

print(f"成功: {len(ok)}  失败: {len(err)}")

# 看前3个错误的详情
print("\n前3个失败详情:")
for r in err[:3]:
    print(f"  {r['_folder']}: {r.get('_error', '未知')}")

# 路径格式对比
print("\n路径格式:")
print(f"  Excel路径示例: {data[0].get('_path', '')}")
print(f"  JSON中路径: {ok[0].get('_path', '') if ok else '?'}")

# 看成功结果的完整字段
if ok:
    r = ok[0]
    print(f"\n成功结果所有key: {list(r.keys())}")
    print(f"_path: {r.get('_path')}")
    print(f"_folder: {r.get('_folder')}")
