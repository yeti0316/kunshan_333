import sys
sys.path.insert(0, '多源项目信息提取器')
from core.excel_reader import read_project_list
p = read_project_list('多源项目信息提取器/工业企业整治测试.xlsx')
print(f'共{len(p)}个项目')
print(f'第1个路径: {p[0]["path"][:100]}')
print(f'第2个路径: {p[1]["path"][:100]}')
# 检查文件是否存在
import os
for i, proj in enumerate(p[:5]):
    exists = os.path.exists(proj["path"])
    print(f'  [{i+1}] exists={exists}  {proj["path"][:80]}')
