import sys
sys.path.insert(0, '多源项目信息提取器')
from core.excel_reader import read_project_list

projects = read_project_list('多源项目信息提取器/工业企业整治测试.xlsx')
print(f'共 {len(projects)} 个项目')
print()

# 看几个示例
for i, p in enumerate(projects[:5]):
    print(f'--- 项目 {i+1} ---')
    print(f'类型: {p["type"]}')
    print(f'路径: {p["path"]}')
    for k, v in p.items():
        if k not in ('path', 'type'):
            print(f'  {k}: {v}')
    print()

# 统计所有列名
all_keys = set()
for p in projects:
    all_keys.update(p.keys())
print(f'所有列名: {all_keys}')

# 统计项目类型分布
type_count = {}
for p in projects:
    t = p["type"]
    type_count[t] = type_count.get(t, 0) + 1
print(f'\n项目类型分布:')
for t, c in type_count.items():
    print(f'  {t}: {c}个')
