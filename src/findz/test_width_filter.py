"""测试 width 过滤器"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from findz.find.find import FileInfo
from datetime import datetime

# 启用图片元数据
FileInfo.enable_image_meta(True)

# 创建一个测试文件信息
test_path = r"E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\test.jpg"

file_info = FileInfo(
    name="test.jpg",
    path=test_path,
    mod_time=datetime.now(),
    size=1024,
    file_type="file",
)

# 获取 getter
getter = file_info.context()

# 测试各个字段
print("测试字段访问：")
print(f"name: {getter('name')}")
print(f"size: {getter('size')}")
print(f"width: {getter('width')}")
print(f"height: {getter('height')}")
print(f"resolution: {getter('resolution')}")

# 测试图片尺寸读取
print("\n测试图片尺寸读取：")
dims = file_info._get_image_dimensions()
print(f"dims: {dims}")

# 检查是否启用
print(f"\n_image_meta_enabled: {FileInfo._image_meta_enabled}")
