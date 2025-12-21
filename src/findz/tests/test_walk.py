"""
walk 模块测试
包含属性测试（Property 2, 3, 4: 缓存命中/失效、并行扫描一致性）
"""

import os
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from findz.filter.filter import create_filter
from findz.find.walk import WalkParams, walk, is_archive, get_default_workers
from findz.find.index_cache import get_global_cache


# ==================== 属性测试 ====================

@settings(max_examples=10, deadline=None)
@given(st.integers(min_value=1, max_value=5))
def test_cache_hit_correctness(num_files):
    """
    Property 2: 缓存命中正确性
    
    *For any* 目录或压缩包，如果其 mtime 未改变，则使用缓存结果应该与重新扫描结果一致
    
    **Validates: Requirements 3.2, 4.2**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        for i in range(num_files):
            (Path(tmpdir) / f"test_{i}.txt").write_text(f"content {i}")
        
        filter_expr = create_filter("1")
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,
            use_cache=True,
        )
        
        # 第一次扫描
        results1 = list(walk(tmpdir, params))
        
        # 第二次扫描（应该使用缓存）
        results2 = list(walk(tmpdir, params))
        
        # 验证结果一致
        paths1 = sorted(f.path for f in results1)
        paths2 = sorted(f.path for f in results2)
        assert paths1 == paths2


@settings(max_examples=5, deadline=None)
@given(st.integers(min_value=1, max_value=3))
def test_cache_invalidation_correctness(num_files):
    """
    Property 3: 缓存失效正确性
    
    *For any* 目录或压缩包，如果其 mtime 已改变，则必须重新扫描而非使用旧缓存
    
    **Validates: Requirements 3.3, 4.3**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        for i in range(num_files):
            (Path(tmpdir) / f"test_{i}.txt").write_text(f"content {i}")
        
        filter_expr = create_filter("1")
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,
            use_cache=True,
        )
        
        # 第一次扫描
        results1 = list(walk(tmpdir, params))
        
        # 添加新文件（修改目录）
        time.sleep(0.1)  # 确保 mtime 变化
        new_file = Path(tmpdir) / "new_file.txt"
        new_file.write_text("new content")
        
        # 第二次扫描（应该检测到变化）
        results2 = list(walk(tmpdir, params))
        
        # 验证新文件被发现
        paths2 = [f.path for f in results2]
        assert str(new_file) in paths2
        assert len(results2) == len(results1) + 1


@settings(max_examples=5, deadline=None)
@given(st.integers(min_value=2, max_value=5))
def test_parallel_scan_consistency(num_files):
    """
    Property 4: 并行扫描结果一致性
    
    *For any* 目录树，并行扫描的结果集合应该与单线程扫描的结果集合相同
    
    **Validates: Requirements 1.1, 1.2**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        for i in range(num_files):
            (Path(tmpdir) / f"test_{i}.txt").write_text(f"content {i}")
        
        # 创建测试压缩包
        zip_path = Path(tmpdir) / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for i in range(num_files):
                zf.writestr(f"inner_{i}.txt", f"inner content {i}")
        
        filter_expr = create_filter("1")
        
        # 单线程扫描
        params_single = WalkParams(
            filter_expr=filter_expr,
            use_cache=False,
            max_workers=1,
        )
        results_single = list(walk(tmpdir, params_single))
        
        # 多线程扫描
        params_parallel = WalkParams(
            filter_expr=filter_expr,
            use_cache=False,
            max_workers=4,
        )
        results_parallel = list(walk(tmpdir, params_parallel))
        
        # 验证结果集合相同（顺序可能不同）
        paths_single = set(f.path for f in results_single)
        paths_parallel = set(f.path for f in results_parallel)
        assert paths_single == paths_parallel


# ==================== 单元测试 ====================

def test_is_archive():
    """测试压缩包检测"""
    assert is_archive("test.zip") is True
    assert is_archive("test.ZIP") is True
    assert is_archive("test.tar.gz") is True
    assert is_archive("test.7z") is True
    assert is_archive("test.rar") is True
    assert is_archive("test.txt") is False
    assert is_archive("test.py") is False


def test_get_default_workers():
    """测试默认 workers 数量"""
    workers = get_default_workers()
    assert 1 <= workers <= 4
    assert workers <= (os.cpu_count() or 1)


def test_walk_basic():
    """测试基本遍历"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        (Path(tmpdir) / "a.txt").write_text("a")
        (Path(tmpdir) / "b.py").write_text("b")
        
        filter_expr = create_filter("1")
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,
            use_cache=False,
        )
        
        results = list(walk(tmpdir, params))
        
        # 应该找到 2 个文件
        file_results = [r for r in results if r.file_type == 'file']
        assert len(file_results) == 2


def test_walk_with_filter():
    """测试带过滤器的遍历"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        (Path(tmpdir) / "a.txt").write_text("a")
        (Path(tmpdir) / "b.py").write_text("b")
        
        filter_expr = create_filter("ext = 'txt'")
        params = WalkParams(
            filter_expr=filter_expr,
            no_archive=True,
            use_cache=False,
        )
        
        results = list(walk(tmpdir, params))
        
        # 应该只找到 1 个 txt 文件
        assert len(results) == 1
        assert results[0].name == "a.txt"


def test_walk_archives_only():
    """测试只返回压缩包模式"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件和压缩包
        (Path(tmpdir) / "a.txt").write_text("a")
        
        zip_path = Path(tmpdir) / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("inner.txt", "inner")
        
        filter_expr = create_filter("1")
        params = WalkParams(
            filter_expr=filter_expr,
            archives_only=True,
            use_cache=False,
        )
        
        results = list(walk(tmpdir, params))
        
        # 应该只返回压缩包
        assert len(results) == 1
        assert results[0].name == "test.zip"


def test_walk_in_archive():
    """测试压缩包内搜索"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建压缩包
        zip_path = Path(tmpdir) / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("a.txt", "content a")
            zf.writestr("b.jpg", "content b")
        
        filter_expr = create_filter("ext = 'txt'")
        params = WalkParams(
            filter_expr=filter_expr,
            use_cache=False,
        )
        
        results = list(walk(tmpdir, params))
        
        # 应该找到压缩包内的 txt 文件
        txt_files = [r for r in results if r.name == "a.txt"]
        assert len(txt_files) == 1
        assert txt_files[0].archive == str(zip_path)


def test_walk_params_default_workers():
    """测试 WalkParams 默认 workers"""
    filter_expr = create_filter("1")
    
    # 不指定 workers
    params = WalkParams(filter_expr=filter_expr)
    assert params.max_workers == get_default_workers()
    
    # 指定 workers
    params = WalkParams(filter_expr=filter_expr, max_workers=2)
    assert params.max_workers == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
