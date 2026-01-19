"""测试查找高度为 630 的图片"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import FileInfo
from findz.api import search

# 启用图片元数据
FileInfo.enable_image_meta(True)

# 测试路径
base_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)'

print(f"查找高度为 630 的图片...")
print(f"路径: {base_path}")
print()

try:
    # 先找所有 avif 文件
    all_files = list(search(
        paths=[base_path],
        where="ext = 'avif'",
        no_archive=False,
    ))
    
    print(f"总共找到 {len(all_files)} 个 avif 文件")
    print("\n前 10 个文件的尺寸:")
    
    # 显示前 10 个文件的尺寸
    for i, file_info in enumerate(all_files[:10]):
        dims = file_info._get_image_dimensions()
        if dims:
            print(f"{i+1}. {file_info.name}: {dims.width}x{dims.height}")
        else:
            print(f"{i+1}. {file_info.name}: 无法读取")
    
    # 手动筛选高度为 630 的
    print("\n查找高度为 630 的图片...")
    height_630 = []
    for file_info in all_files:
        dims = file_info._get_image_dimensions()
        if dims and dims.height == 630:
            height_630.append(file_info)
            print(f"  ✓ {file_info.name} ({dims.resolution})")
            if len(height_630) >= 5:
                break
    
    print(f"\n找到 {len(height_630)} 个高度为 630 的图片")
    
    # 现在用过滤器查找
    print("\n使用过滤器查找...")
    filtered = list(search(
        paths=[base_path],
        where="height = 630",
        no_archive=False,
    ))
    
    print(f"过滤器找到 {len(filtered)} 个文件")
    for file_info in filtered[:5]:
        dims = file_info._get_image_dimensions()
        if dims:
            print(f"  - {file_info.name} ({dims.resolution})")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
