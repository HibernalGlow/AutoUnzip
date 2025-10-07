"""
创建测试用的嵌套压缩包
"""

import zipfile
import tarfile
import os
from pathlib import Path

# 创建测试目录
test_dir = Path("D:/test_nested_archives")
test_dir.mkdir(exist_ok=True)

# 1. 创建一些普通文件
(test_dir / "file1.txt").write_text("This is file 1")
(test_dir / "file2.txt").write_text("This is file 2")

# 2. 创建一个内部 ZIP
inner_zip = test_dir / "inner.zip"
with zipfile.ZipFile(inner_zip, 'w') as zf:
    zf.writestr("inner_file1.txt", "Inner content 1")
    zf.writestr("inner_file2.txt", "Inner content 2")

# 3. 创建包含 ZIP 的外层 ZIP (嵌套压缩包!)
outer_zip1 = test_dir / "outer1.zip"
with zipfile.ZipFile(outer_zip1, 'w') as zf:
    zf.write(test_dir / "file1.txt", "file1.txt")
    zf.write(inner_zip, "nested/inner.zip")  # 包含另一个 ZIP！
    zf.writestr("readme.txt", "This archive contains a nested zip")

# 4. 创建另一个包含 TAR 的 ZIP
inner_tar = test_dir / "inner.tar.gz"
with tarfile.open(inner_tar, 'w:gz') as tf:
    info = tarfile.TarInfo("inner_tar_file.txt")
    info.size = 10
    import io
    tf.addfile(info, io.BytesIO(b"Tar file!!"))

outer_zip2 = test_dir / "outer2.zip"
with zipfile.ZipFile(outer_zip2, 'w') as zf:
    zf.write(test_dir / "file2.txt", "file2.txt")
    zf.write(inner_tar, "archives/data.tar.gz")  # 包含 TAR.GZ！
    zf.writestr("info.txt", "This contains tar.gz")

# 5. 创建不含嵌套压缩包的普通 ZIP
simple_zip = test_dir / "simple.zip"
with zipfile.ZipFile(simple_zip, 'w') as zf:
    zf.write(test_dir / "file1.txt", "file1.txt")
    zf.write(test_dir / "file2.txt", "file2.txt")
    zf.writestr("normal.txt", "Just normal files")

# 清理临时文件
inner_zip.unlink()
inner_tar.unlink()

print(f"测试数据已创建在: {test_dir}")
print("\n创建的文件:")
print(f"  outer1.zip  - 包含嵌套的 inner.zip")
print(f"  outer2.zip  - 包含嵌套的 data.tar.gz")
print(f"  simple.zip  - 不包含嵌套压缩包")
print(f"  file1.txt")
print(f"  file2.txt")
