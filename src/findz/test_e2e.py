"""端到端测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import FileInfo
from findz.find.walk import walk, WalkParams
from findz.filter.filter import create_filter

# 启用图片元数据
FileInfo.enable_image_meta(True)
print(f"图片元数据已启用: {FileInfo._image_meta_enabled}")

# 测试路径
base_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)'

print("端到端测试...")
print(f"路径: {base_path}")
print()

try:
    # 先测试不带过滤器的遍历
    print("测试 1: 遍历所有 avif 文件...")
    filter_expr1 = create_filter("ext = 'avif'")
    params1 = WalkParams(
        filter_expr=filter_expr1,
        follow_symlinks=False,
        no_archive=False,
        archives_only=False,
        use_cache=True,
        max_workers=4,
    )
    
    count1 = 0
    for file_info in walk(base_path, params1):
        count1 += 1
        if count1 <= 3:
            print(f"  文件: {file_info.name}")
            print(f"    容器: {file_info.container}")
            print(f"    archive: {file_info.archive}")
            print(f"    路径: {file_info.path}")
            dims = file_info._get_image_dimensions()
            if dims:
                print(f"    尺寸: {dims.width}x{dims.height}")
            else:
                print(f"    尺寸: 无法读取")
        if count1 >= 10:
            break
    
    print(f"找到 {count1} 个 avif 文件\n")
    
    # 测试带高度过滤的遍历
    print("测试 2: 遍历高度为 630 的文件...")
    filter_expr2 = create_filter("height = 630")
    params2 = WalkParams(
        filter_expr=filter_expr2,
        follow_symlinks=False,
        no_archive=False,
        archives_only=False,
        use_cache=True,
        max_workers=4,
    )
    
    count2 = 0
    for file_info in walk(base_path, params2):
        count2 += 1
        dims = file_info._get_image_dimensions()
        if dims:
            print(f"  {file_info.name}: {dims.width}x{dims.height}")
        else:
            print(f"  {file_info.name}: 无尺寸")
        
        if count2 >= 10:
            break
    
    print(f"找到 {count2} 个高度为 630 的文件")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
