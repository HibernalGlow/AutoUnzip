"""
缓存模块测试
包含属性测试（Property 1: 序列化 Round-Trip）
"""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from findz.find.cache import CacheManager, get_cache_manager


# ==================== 属性测试 ====================

# 生成随机文件信息字典的策略
file_info_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    'path': st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    'size': st.integers(min_value=0, max_value=10**12),
    'mod_time': st.floats(min_value=0, max_value=2**31).map(
        lambda x: __import__('datetime').datetime.fromtimestamp(x).isoformat()
    ),
    'type': st.sampled_from(['file', 'dir', 'link']),
    'container': st.text(max_size=100),
    'archive': st.text(max_size=100),
    'ext': st.text(max_size=10),
})


@given(st.lists(file_info_strategy, min_size=0, max_size=100))
@settings(max_examples=100, deadline=None)
def test_serialization_roundtrip(results):
    """
    Property 1: 序列化 Round-Trip
    
    *For any* 搜索结果列表，序列化后再反序列化应该产生等价的数据
    
    **Validates: Requirements 2.5**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        # 保存
        cache.save_results(results, metadata={'test': True})
        
        # 加载
        loaded = cache.load_results()
        
        assert loaded is not None
        assert loaded['count'] == len(results)
        assert len(loaded['files']) == len(results)
        
        # 验证每个文件的关键字段
        for orig, loaded_file in zip(results, loaded['files']):
            assert loaded_file['name'] == orig['name']
            assert loaded_file['path'] == orig['path']
            assert loaded_file['size'] == orig['size']
            assert loaded_file['type'] == orig['type']
            # ext 可能被处理过，只检查存在
            assert 'ext' in loaded_file


# ==================== 单元测试 ====================

def test_cache_manager_init():
    """测试缓存管理器初始化"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        assert cache.cache_dir.exists()


def test_save_and_load_empty():
    """测试空结果的保存和加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        cache.save_results([])
        loaded = cache.load_results()
        
        assert loaded is not None
        assert loaded['count'] == 0
        assert loaded['files'] == []


def test_save_and_load_with_metadata():
    """测试带元数据的保存和加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        results = [{'name': 'test.txt', 'path': '/test.txt', 'size': 100,
                    'mod_time': '2025-01-01T00:00:00', 'type': 'file',
                    'container': '', 'archive': '', 'ext': 'txt'}]
        metadata = {'where': "ext = 'txt'", 'paths': ['/test']}
        
        cache.save_results(results, metadata)
        loaded = cache.load_results()
        
        assert loaded['metadata'] == metadata


def test_dir_mtime_cache():
    """测试目录 mtime 缓存"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        # 设置 mtime
        cache.set_dir_mtime('/some/path', 12345.0)
        assert cache.get_dir_mtime('/some/path') == 12345.0
        
        # 不存在的路径
        assert cache.get_dir_mtime('/nonexistent') is None


def test_is_dir_changed():
    """测试目录变更检测"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        # 创建测试目录
        test_dir = Path(tmpdir) / "test_dir"
        test_dir.mkdir()
        
        # 首次检查应该返回 True（不在缓存中）
        assert cache.is_dir_changed(str(test_dir)) is True
        
        # 缓存 mtime
        mtime = os.stat(test_dir).st_mtime
        cache.set_dir_mtime(str(test_dir), mtime)
        
        # 再次检查应该返回 False（未修改）
        assert cache.is_dir_changed(str(test_dir)) is False


def test_clear_cache():
    """测试清空缓存"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(cache_dir=Path(tmpdir))
        
        # 保存一些数据
        cache.save_results([{'name': 'test', 'path': '/test', 'size': 0,
                            'mod_time': '2025-01-01T00:00:00', 'type': 'file',
                            'container': '', 'archive': '', 'ext': ''}])
        cache.set_dir_mtime('/test', 12345.0)
        cache.flush()
        
        # 清空
        cache.clear()
        
        # 验证已清空
        assert cache.load_results() is None
        assert cache.get_dir_mtime('/test') is None


def test_format_size():
    """测试文件大小格式化"""
    assert CacheManager._format_size(0) == '0B'
    assert CacheManager._format_size(1023) == '1023B'
    assert CacheManager._format_size(1024) == '1.0KB'
    assert CacheManager._format_size(1024 * 1024) == '1.0MB'
    assert CacheManager._format_size(1024 * 1024 * 1024) == '1.0GB'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
