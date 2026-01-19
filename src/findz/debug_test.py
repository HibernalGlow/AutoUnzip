"""直接调试测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 测试 1: 缓存功能
print("=== 测试缓存功能 ===")
from filter.image_meta import get_image_dimensions_cached, get_image_dimensions, ImageDimensions
from unittest.mock import patch

get_image_dimensions_cached.cache_clear()
print("Cache cleared")

# 测试 2: FileInfo 集成
print("\n=== 测试 FileInfo 集成 ===")
try:
    from find.find import FileInfo
    print(f"FileInfo imported, _image_meta_enabled = {FileInfo._image_meta_enabled}")
    
    FileInfo.enable_image_meta(True)
    print(f"After enable: _image_meta_enabled = {FileInfo._image_meta_enabled}")
    
    from datetime import datetime
    file_info = FileInfo(
        name="test.jpg",
        path="/fake/path/test.jpg",
        mod_time=datetime.now(),
        size=1024,
        file_type="file",
    )
    
    getter = file_info.context()
    print(f"width = {getter('width')}")
    print(f"height = {getter('height')}")
    print("FileInfo integration OK")
    
    FileInfo.enable_image_meta(False)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# 测试 3: 真实图片
print("\n=== 测试真实图片 ===")
try:
    from PIL import Image
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmp:
        png_path = Path(tmp) / "test.png"
        img = Image.new('RGB', (1200, 630), color='red')
        img.save(png_path)
        print(f"Created {png_path}")
        
        dims = get_image_dimensions(str(png_path))
        print(f"dims = {dims}")
        if dims:
            print(f"  width={dims.width}, height={dims.height}, resolution={dims.resolution}")
        
except ImportError:
    print("Pillow not installed, skipping")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 完成 ===")
