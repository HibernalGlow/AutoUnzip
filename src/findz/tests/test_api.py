"""
API 模块测试
包含属性测试（Property 6: 流式输出正确性）
"""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from findz.api import (
    search, search_cached, load_cache, group_by, refine,
    sort_groups, clear_cache, file_info_to_dict,
    parse_refine_filter, apply_refine_filter
)
from findz.find.cache import CacheManager


# ==================== 属性测试 ====================

@settings(max_examples=10, deadline=None)
@given(st.integers(min_value=1, max_value=5))
def test_streaming_correctness(num_files):
    """
    Property 6: 流式输出正确性
    
    *For any* 搜索操作，流式迭代器产生的结果应该与收集全部结果后的列表一致
    
    **Validates: Requirements 5.1**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        for i in range(num_files):
            (Path(tmpdir) / f"test_{i}.txt").write_text(f"content {i}")
        
        # 流式收集
        streaming_results = []
        for file_info in search([tmpdir], where="1", no_archive=True, use_cache=False):
            streaming_results.append(file_info)
        
        # 再次搜索并一次性收集
        batch_results = list(search([tmpdir], where="1", no_archive=True, use_cache=False))
        
        # 验证数量一致
        assert len(streaming_results) == len(batch_results)
        
        # 验证内容一致（按路径排序后比较）
        streaming_paths = sorted(f.path for f in streaming_results)
        batch_paths = sorted(f.path for f in batch_results)
        assert streaming_paths == batch_paths


# ==================== 单元测试 ====================

def test_search_basic():
    """测试基本搜索"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        (Path(tmpdir) / "test.txt").write_text("hello")
        (Path(tmpdir) / "test.py").write_text("print('hi')")
        
        # 搜索所有文件
        results = list(search([tmpdir], where="1", no_archive=True, use_cache=False))
        assert len(results) >= 2
        
        # 按扩展名搜索
        results = list(search([tmpdir], where="ext = 'txt'", no_archive=True, use_cache=False))
        assert len(results) == 1
        assert results[0].name == "test.txt"


def test_search_cached_and_load():
    """测试缓存搜索和加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        test_dir = Path(tmpdir) / "files"
        test_dir.mkdir()
        
        # 创建测试文件
        (test_dir / "a.txt").write_text("a")
        (test_dir / "b.txt").write_text("b")
        
        cache = CacheManager(cache_dir=cache_dir)
        
        # 搜索并缓存
        results = search_cached(
            [str(test_dir)],
            where="1",
            no_archive=True,
            use_cache=False,
            cache_manager=cache
        )
        assert len(results) >= 2
        
        # 加载缓存
        loaded = load_cache(cache_manager=cache)
        assert loaded is not None
        assert len(loaded) == len(results)


def test_group_by_ext():
    """测试按扩展名分组"""
    files = [
        {'name': 'a.jpg', 'path': '/a.jpg', 'size': 100, 'ext': 'jpg'},
        {'name': 'b.jpg', 'path': '/b.jpg', 'size': 200, 'ext': 'jpg'},
        {'name': 'c.png', 'path': '/c.png', 'size': 300, 'ext': 'png'},
    ]
    
    groups = group_by(files, 'ext')
    
    assert len(groups) == 2
    
    jpg_group = next(g for g in groups if g['key'] == 'jpg')
    assert jpg_group['count'] == 2
    assert jpg_group['total_size'] == 300
    assert jpg_group['avg_size'] == 150


def test_group_by_archive():
    """测试按压缩包分组"""
    files = [
        {'name': 'a.jpg', 'path': '/a.jpg', 'size': 100, 'archive': '/test.zip', 'ext': 'jpg'},
        {'name': 'b.jpg', 'path': '/b.jpg', 'size': 200, 'archive': '/test.zip', 'ext': 'jpg'},
        {'name': 'c.png', 'path': '/c.png', 'size': 300, 'archive': '/other.zip', 'ext': 'png'},
    ]
    
    groups = group_by(files, 'archive')
    
    assert len(groups) == 2


def test_refine():
    """测试二次筛选"""
    groups = [
        {'key': '/a.zip', 'count': 10, 'avg_size': 1000, 'total_size': 10000},
        {'key': '/b.zip', 'count': 5, 'avg_size': 2000, 'total_size': 10000},
        {'key': '/c.zip', 'count': 20, 'avg_size': 500, 'total_size': 10000},
    ]
    
    # 筛选 count > 8
    result = refine(groups, 'count > 8')
    assert len(result) == 2
    
    # 筛选 avg_size > 1500
    result = refine(groups, 'avg_size > 1500')
    assert len(result) == 1
    assert result[0]['key'] == '/b.zip'


def test_parse_refine_filter():
    """测试筛选表达式解析"""
    # 简单条件
    result = parse_refine_filter('count > 10')
    assert result['count']['op'] == '>'
    assert result['count']['value'] == 10
    
    # 大小单位
    result = parse_refine_filter('avg_size > 1M')
    assert result['avg_size']['value'] == 1024 * 1024
    
    # 多条件
    result = parse_refine_filter('count > 5 AND avg_size > 1K')
    assert 'count' in result
    assert 'avg_size' in result


def test_sort_groups():
    """测试排序"""
    groups = [
        {'name': 'a', 'count': 10, 'avg_size': 100},
        {'name': 'b', 'count': 5, 'avg_size': 200},
        {'name': 'c', 'count': 15, 'avg_size': 50},
    ]
    
    # 按 count 降序
    sorted_groups = sort_groups(groups.copy(), 'count', descending=True)
    assert sorted_groups[0]['name'] == 'c'
    
    # 按 avg_size 升序
    sorted_groups = sort_groups(groups.copy(), 'avg_size', descending=False)
    assert sorted_groups[0]['name'] == 'c'


def test_clear_cache():
    """测试清空缓存"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        # 保存一些数据
        cache.save_results([{'name': 'test', 'path': '/test', 'size': 0,
                            'mod_time': '2025-01-01T00:00:00', 'type': 'file',
                            'container': '', 'archive': '', 'ext': ''}])
        
        # 清空
        clear_cache(cache_manager=cache)
        
        # 验证
        assert load_cache(cache_manager=cache) is None


def test_file_info_to_dict():
    """测试 FileInfo 转字典"""
    from findz.find.find import FileInfo
    from datetime import datetime
    
    fi = FileInfo(
        name='test.txt',
        path='/path/to/test.txt',
        mod_time=datetime(2025, 1, 1, 12, 0, 0),
        size=1024,
        file_type='file',
        container='/archive.zip',
        archive='/archive.zip',
    )
    
    d = file_info_to_dict(fi)
    
    assert d['name'] == 'test.txt'
    assert d['size'] == 1024
    assert d['ext'] == 'txt'
    assert d['archive'] == '/archive.zip'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
