"""
pytest fixtures for bandia tests
"""

import zipfile
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tmp_archive(tmp_dir: Path) -> Path:
    """创建临时测试压缩包（单根目录）"""
    # 创建源文件
    content_dir = tmp_dir / "source"
    content_dir.mkdir()
    (content_dir / "test_folder").mkdir()
    (content_dir / "test_folder" / "file1.txt").write_text("Hello", encoding="utf-8")
    (content_dir / "test_folder" / "file2.txt").write_text("World", encoding="utf-8")
    
    # 创建压缩包
    archive_path = tmp_dir / "test_single_root.zip"
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.write(content_dir / "test_folder" / "file1.txt", "test_folder/file1.txt")
        zf.write(content_dir / "test_folder" / "file2.txt", "test_folder/file2.txt")
    
    return archive_path


@pytest.fixture
def tmp_archive_multi_root(tmp_dir: Path) -> Path:
    """创建临时测试压缩包（多根项）"""
    content_dir = tmp_dir / "source"
    content_dir.mkdir(exist_ok=True)
    (content_dir / "file1.txt").write_text("Hello", encoding="utf-8")
    (content_dir / "file2.txt").write_text("World", encoding="utf-8")
    
    archive_path = tmp_dir / "test_multi_root.zip"
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.write(content_dir / "file1.txt", "file1.txt")
        zf.write(content_dir / "file2.txt", "file2.txt")
    
    return archive_path


@pytest.fixture
def bz_path():
    """获取 Bandizip 可执行文件路径"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from bandia.utils import find_bz_executable
    
    path = find_bz_executable()
    if not path:
        pytest.skip("Bandizip (bz.exe) not found")
    return path
