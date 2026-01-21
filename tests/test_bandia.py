"""
bandia 测试用例
"""

import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


class TestExtractMode:
    """测试解压模式"""
    
    def test_extract_single_auto(self, tmp_archive, tmp_dir, bz_path):
        """测试智能解压（单根目录）"""
        from bandia.core import extract_single
        from bandia.types import ExtractMode
        
        result = extract_single(
            archive=tmp_archive,
            bz_path=bz_path,
            delete=False,
            extract_mode=ExtractMode.AUTO
        )
        
        assert result.success
        assert result.output_path is not None
        # 单根目录应该解压到 test_folder
        assert result.output_path.name == "test_folder"
        assert result.output_path.exists()
        assert (result.output_path / "file1.txt").exists()
    
    def test_extract_single_auto_multi_root(self, tmp_archive_multi_root, tmp_dir, bz_path):
        """测试智能解压（多根项）"""
        from bandia.core import extract_single
        from bandia.types import ExtractMode
        
        result = extract_single(
            archive=tmp_archive_multi_root,
            bz_path=bz_path,
            delete=False,
            extract_mode=ExtractMode.AUTO
        )
        
        assert result.success
        assert result.output_path is not None
        # 多根项应该创建与压缩包同名的目录
        assert result.output_path.name == "test_multi_root"
    
    def test_extract_single_normal(self, tmp_archive, tmp_dir, bz_path):
        """测试普通解压（带前缀）"""
        from bandia.core import extract_single
        from bandia.types import ExtractMode
        
        result = extract_single(
            archive=tmp_archive,
            bz_path=bz_path,
            delete=False,
            extract_mode=ExtractMode.NORMAL,
            output_prefix="[a]"
        )
        
        assert result.success
        assert result.output_path is not None
        # 普通模式应该解压到 [a]压缩包名 目录
        assert result.output_path.name == "[a]test_single_root"
        assert result.output_path.exists()
    
    def test_extract_single_normal_custom_prefix(self, tmp_archive, tmp_dir, bz_path):
        """测试普通解压（自定义前缀）"""
        from bandia.core import extract_single
        from bandia.types import ExtractMode
        
        result = extract_single(
            archive=tmp_archive,
            bz_path=bz_path,
            delete=False,
            extract_mode=ExtractMode.NORMAL,
            output_prefix="extracted_"
        )
        
        assert result.success
        assert result.output_path is not None
        assert result.output_path.name == "extracted_test_single_root"


class TestBatchExtract:
    """测试批量解压"""
    
    def test_extract_batch(self, tmp_archive, tmp_archive_multi_root, bz_path):
        """测试批量解压"""
        from bandia.core import extract_batch
        
        result = extract_batch(
            paths=[tmp_archive, tmp_archive_multi_root],
            delete=False,
            parallel=False
        )
        
        assert result.success
        assert result.extracted == 2
        assert result.failed == 0
        assert len(result.results) == 2


class TestPathMapping:
    """测试路径映射"""
    
    def test_path_mapping_export(self, tmp_archive, bz_path):
        """测试解压后的路径映射"""
        from bandia.core import extract_single
        from bandia.types import ExtractMode
        
        result = extract_single(
            archive=tmp_archive,
            bz_path=bz_path,
            delete=False,
            extract_mode=ExtractMode.AUTO
        )
        
        assert result.success
        assert result.output_path is not None
        
        # 验证映射关系
        assert result.path == tmp_archive
        assert result.output_path.exists()


class TestCompress:
    """测试压缩功能"""
    
    def test_compress_single(self, tmp_dir, bz_path):
        """测试单目录压缩"""
        from bandia.core import compress_single
        
        # 创建源目录
        source = tmp_dir / "to_compress"
        source.mkdir()
        (source / "file.txt").write_text("test content", encoding="utf-8")
        
        archive = tmp_dir / "output.zip"
        
        result = compress_single(
            source=source,
            archive_path=archive,
            bz_path=bz_path,
            delete_source=False
        )
        
        assert result.success
        assert archive.exists()
        assert source.exists()  # 不删除源目录
    
    def test_compress_with_delete(self, tmp_dir, bz_path):
        """测试压缩后删除源目录"""
        from bandia.core import compress_single
        
        source = tmp_dir / "to_delete"
        source.mkdir()
        (source / "file.txt").write_text("test", encoding="utf-8")
        
        archive = tmp_dir / "deleted.zip"
        
        result = compress_single(
            source=source,
            archive_path=archive,
            bz_path=bz_path,
            delete_source=True
        )
        
        assert result.success
        assert archive.exists()
        # 使用 -sdel 后源目录应该被删除
        # 注意：bz.exe -sdel 可能不会删除目录本身，只删除内容


class TestTypes:
    """测试类型定义"""
    
    def test_extract_mode_enum(self):
        """测试 ExtractMode 枚举"""
        from bandia.types import ExtractMode
        
        assert ExtractMode.AUTO.value == "auto"
        assert ExtractMode.NORMAL.value == "normal"
    
    def test_path_mapping_dataclass(self):
        """测试 PathMapping 数据类"""
        from bandia.types import PathMapping
        
        mapping = PathMapping(
            archive_path="/path/to/archive.zip",
            extracted_path="/path/to/folder"
        )
        
        assert mapping.archive_path == "/path/to/archive.zip"
        assert mapping.extracted_path == "/path/to/folder"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
