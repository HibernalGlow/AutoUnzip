"""
查找包含嵌套压缩包的外层压缩包
"""

import sys

from .filter.filter import create_filter
from .find.walk import WalkParams, walk, is_archive

def find_nested_archives(search_path):
    """查找包含嵌套压缩包的外层压缩包"""
    
    # 创建匹配所有文件的过滤器
    filter_expr = create_filter("1")
    
    # 配置参数
    params = WalkParams(
        filter_expr=filter_expr,
        follow_symlinks=False,
        no_archive=False,  # 必须扫描压缩包内部
        archives_only=False,
        use_cache=True,
        max_workers=4,
        error_handler=lambda msg: print(f"错误: {msg}", file=sys.stderr),
    )
    
    # 收集包含嵌套压缩包的外层压缩包
    nested_containers = set()
    
    print("搜索中...")
    count = 0
    for file_info in walk(search_path, params):
        count += 1
        # 检查是否在压缩包内（container 不为空）
        if file_info.container:
            # 检查文件本身是否是压缩包
            if is_archive(file_info.name):
                print(f"找到嵌套: {file_info.name} 在 {file_info.container}")
                nested_containers.add(file_info.container)
    
    print(f"\n共扫描 {count} 个文件")
    print(f"找到 {len(nested_containers)} 个包含嵌套压缩包的外层压缩包:\n")
    
    for container in sorted(nested_containers):
        print(container)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m findz.find_nested <搜索路径>")
        sys.exit(1)
    
    find_nested_archives(sys.argv[1])
