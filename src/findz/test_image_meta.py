"""测试图片元数据模块"""
import sys
sys.path.insert(0, '.')

from filter.image_meta import (
    get_image_dimensions, 
    IMAGE_EXTENSIONS,
    IMAGESIZE_EXTENSIONS,
    PILLOW_EXTENSIONS,
)

print("=== 图片元数据模块测试 ===")
print(f"IMAGE_EXTENSIONS: {len(IMAGE_EXTENSIONS)} 种格式")
print(f"  - imagesize 支持: {IMAGESIZE_EXTENSIONS}")
print(f"  - pillow 支持: {PILLOW_EXTENSIONS}")
print()

# 测试 FileInfo 扩展
from find.find import FileInfo

print("=== FileInfo 扩展测试 ===")
print(f"_image_meta_enabled: {FileInfo._image_meta_enabled}")

# 启用图片元数据
FileInfo.enable_image_meta(True)
print(f"启用后 _image_meta_enabled: {FileInfo._image_meta_enabled}")

print()
print("✅ 模块加载成功！")
