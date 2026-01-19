"""测试压缩包内图片宽度查找"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import FileInfo, list_files_in_zip
from datetime import datetime

# 启用图片元数据
FileInfo.enable_image_meta(True)

# 测试路径
zip_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\2019 [Nameless (鬼針草)].zip'

print(f"测试压缩包: {zip_path}")
print(f"文件存在: {Path(zip_path).exists()}")
print()

# 直接列出压缩包内容
print("直接列出压缩包内容...")
try:
    files = list_files_in_zip(zip_path)
    print(f"找到 {len(files)} 个文件")
    
    # 找出图片文件
    image_files = [f for f in files if f.name.lower().endswith(('.jpg', '.jpeg', '.png', '.avif', '.webp'))]
    print(f"其中图片文件: {len(image_files)} 个")
    
    # 测试前几个图片的尺寸读取
    print("\n测试图片尺寸读取:")
    for i, file_info in enumerate(image_files[:5]):
        print(f"\n{i+1}. {file_info.name}")
        print(f"   大小: {file_info.size} bytes")
        print(f"   容器: {file_info.container}")
        print(f"   路径: {file_info.path}")
        
        # 读取图片尺寸
        dims = file_info._get_image_dimensions()
        if dims:
            print(f"   ✓ 宽度: {dims.width}")
            print(f"   ✓ 高度: {dims.height}")
            print(f"   ✓ 分辨率: {dims.resolution}")
        else:
            print(f"   ✗ 无法读取图片尺寸")
    
    # 统计宽度为 630 的图片
    print("\n\n查找宽度为 630 的图片...")
    count_630 = 0
    for file_info in image_files:
        dims = file_info._get_image_dimensions()
        if dims and dims.width == 630:
            count_630 += 1
            print(f"  找到: {file_info.name} ({dims.resolution})")
    
    print(f"\n总共找到 {count_630} 个宽度为 630 的图片")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
