"""测试从压缩包读取文件数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import list_files_in_zip
from findz.filter.image_meta import get_image_dimensions_from_bytes

# 测试路径
zip_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\2019 [Nameless (鬼針草)].zip'

print("测试从压缩包读取图片数据...")

try:
    files = list_files_in_zip(zip_path)
    image_files = [f for f in files if f.name.lower().endswith(('.avif', '.jpg', '.png'))]
    
    if image_files:
        file_info = image_files[0]
        print(f"\n测试文件: {file_info.name}")
        print(f"容器: {file_info.container}")
        print(f"路径: {file_info.path}")
        print(f"大小: {file_info.size}")
        
        # 测试 _read_from_archive
        print("\n调用 _read_from_archive...")
        data = file_info._read_from_archive()
        
        if data:
            print(f"✓ 成功读取 {len(data)} 字节")
            
            # 测试从字节流读取图片尺寸
            print("\n调用 get_image_dimensions_from_bytes...")
            dims = get_image_dimensions_from_bytes(data, file_info.name)
            
            if dims:
                print(f"✓ 成功读取图片尺寸:")
                print(f"  宽度: {dims.width}")
                print(f"  高度: {dims.height}")
                print(f"  分辨率: {dims.resolution}")
            else:
                print("✗ 无法从字节流读取图片尺寸")
        else:
            print("✗ 无法从压缩包读取数据")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
