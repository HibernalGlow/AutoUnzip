"""调试过滤器问题"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import FileInfo, list_files_in_zip
from findz.filter.filter import create_filter
from datetime import datetime

# 启用图片元数据
FileInfo.enable_image_meta(True)

# 测试路径
zip_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\2019 [Nameless (鬼針草)].zip'

print("测试过滤器...")

try:
    files = list_files_in_zip(zip_path)
    image_files = [f for f in files if f.name.lower().endswith('.avif')]
    
    print(f"找到 {len(image_files)} 个 avif 文件")
    
    # 测试第一个文件
    if image_files:
        file_info = image_files[0]
        print(f"\n测试文件: {file_info.name}")
        
        # 读取尺寸
        dims = file_info._get_image_dimensions()
        if dims:
            print(f"尺寸: {dims.width}x{dims.height}")
        else:
            print("无法读取尺寸")
        
        # 测试 getter
        getter = file_info.context()
        print(f"\ngetter('width'): {getter('width')}")
        print(f"getter('height'): {getter('height')}")
        
        # 测试过滤器
        filter_expr = create_filter("height = 630")
        matches, error = filter_expr.test(getter)
        print(f"\n过滤器 'height = 630' 结果: {matches}")
        if error:
            print(f"错误: {error}")
        
        # 测试另一个过滤器
        filter_expr2 = create_filter("height > 0")
        matches2, error2 = filter_expr2.test(getter)
        print(f"\n过滤器 'height > 0' 结果: {matches2}")
        if error2:
            print(f"错误: {error2}")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
