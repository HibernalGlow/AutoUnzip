"""测试 CLI 的 JSON 输出和二次筛选功能"""

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from findz.cli import (
    app,
    group_files,
    save_results_cache,
    load_results_cache,
)
# 从 api.py 导入核心函数
from findz.api import (
    file_info_to_dict,
    parse_refine_filter,
    apply_refine_filter,
)


runner = CliRunner()


class TestFileInfoToDict:
    """测试 FileInfo 转字典"""
    
    def test_basic_conversion(self):
        """基本转换测试"""
        from findz.find.find import FileInfo
        from datetime import datetime
        
        info = FileInfo(
            name="test.jpg",
            path="/path/to/test.jpg",
            size=1024,
            mod_time=datetime(2024, 1, 15, 10, 30, 0),
            file_type="file",
            container=None,
            archive=None,
        )
        
        result = file_info_to_dict(info)
        
        assert result['name'] == "test.jpg"
        assert result['size'] == 1024
        assert result['ext'] == "jpg"
        assert result['date'] == "2024-01-15"
        assert result['container'] == ''


class TestGroupFiles:
    """测试文件分组功能"""
    
    @pytest.fixture
    def sample_files(self):
        return [
            {'name': 'a.jpg', 'path': 'a.jpg', 'size': 1000, 'ext': 'jpg', 'archive': 'test1.zip', 'container': 'test1.zip'},
            {'name': 'b.jpg', 'path': 'b.jpg', 'size': 2000, 'ext': 'jpg', 'archive': 'test1.zip', 'container': 'test1.zip'},
            {'name': 'c.png', 'path': 'c.png', 'size': 3000, 'ext': 'png', 'archive': 'test1.zip', 'container': 'test1.zip'},
            {'name': 'd.jpg', 'path': 'd.jpg', 'size': 4000, 'ext': 'jpg', 'archive': 'test2.zip', 'container': 'test2.zip'},
            {'name': 'e.png', 'path': 'e.png', 'size': 5000, 'ext': 'png', 'archive': '', 'container': ''},
        ]
    
    def test_group_by_archive(self, sample_files):
        """按压缩包分组"""
        groups = group_files(sample_files, 'archive')
        
        # 应该有 2 个分组（空 archive 的被跳过）
        assert len(groups) == 2
        
        # 找到 test1.zip 分组
        test1 = next(g for g in groups if g['key'] == 'test1.zip')
        assert test1['count'] == 3
        assert test1['total_size'] == 6000
        assert test1['avg_size'] == 2000
    
    def test_group_by_ext(self, sample_files):
        """按扩展名分组"""
        groups = group_files(sample_files, 'ext')
        
        assert len(groups) == 2  # jpg 和 png
        
        jpg_group = next(g for g in groups if g['key'] == 'jpg')
        assert jpg_group['count'] == 3
        
        png_group = next(g for g in groups if g['key'] == 'png')
        assert png_group['count'] == 2


class TestParseRefineFilter:
    """测试二次筛选表达式解析"""
    
    def test_simple_comparison(self):
        """简单比较"""
        result = parse_refine_filter("count > 10")
        assert result['count']['op'] == '>'
        assert result['count']['value'] == 10
    
    def test_size_parsing(self):
        """大小解析"""
        result = parse_refine_filter("avg_size > 1M")
        assert result['avg_size']['op'] == '>'
        assert result['avg_size']['value'] == 1024 * 1024
    
    def test_multiple_conditions(self):
        """多条件"""
        result = parse_refine_filter("count > 5 AND avg_size < 10M")
        assert 'count' in result
        assert 'avg_size' in result
    
    def test_like_operator(self):
        """LIKE 操作符"""
        result = parse_refine_filter("name LIKE test%")
        assert result['name']['op'] == 'LIKE'
        assert result['name']['value'] == 'test%'


class TestApplyRefineFilter:
    """测试应用筛选条件"""
    
    @pytest.fixture
    def sample_groups(self):
        return [
            {'key': 'a.zip', 'name': 'a.zip', 'count': 5, 'avg_size': 1000, 'total_size': 5000},
            {'key': 'b.zip', 'name': 'b.zip', 'count': 15, 'avg_size': 2000000, 'total_size': 30000000},
            {'key': 'c.zip', 'name': 'c.zip', 'count': 3, 'avg_size': 500, 'total_size': 1500},
        ]
    
    def test_filter_by_count(self, sample_groups):
        """按数量筛选"""
        filter_dict = parse_refine_filter("count > 10")
        result = apply_refine_filter(sample_groups, filter_dict)
        
        assert len(result) == 1
        assert result[0]['key'] == 'b.zip'
    
    def test_filter_by_avg_size(self, sample_groups):
        """按平均大小筛选"""
        filter_dict = parse_refine_filter("avg_size > 1M")
        result = apply_refine_filter(sample_groups, filter_dict)
        
        assert len(result) == 1
        assert result[0]['key'] == 'b.zip'
    
    def test_combined_filter(self, sample_groups):
        """组合筛选"""
        filter_dict = parse_refine_filter("count >= 3 AND avg_size < 1M")
        result = apply_refine_filter(sample_groups, filter_dict)
        
        assert len(result) == 2  # a.zip 和 c.zip


class TestResultCache:
    """测试结果缓存"""
    
    def test_save_and_load(self):
        """保存和加载缓存"""
        test_files = [
            {'name': 'test.jpg', 'size': 1000},
            {'name': 'test2.png', 'size': 2000},
        ]
        
        save_results_cache(test_files, {'where': 'ext = jpg', 'paths': ['/test']})
        
        loaded = load_results_cache()
        assert loaded is not None
        assert loaded['count'] == 2
        assert len(loaded['files']) == 2
        assert loaded['metadata']['where'] == 'ext = jpg'


class TestCLIJsonOutput:
    """测试 CLI JSON 输出"""
    
    def test_json_help(self):
        """--json 选项存在"""
        result = runner.invoke(app, ["--help"])
        assert "--json" in result.output
    
    def test_refine_help(self):
        """--refine 选项存在"""
        result = runner.invoke(app, ["--help"])
        assert "--refine" in result.output
        assert "--group-by" in result.output
