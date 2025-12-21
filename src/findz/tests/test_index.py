"""
倒排索引模块测试
包含属性测试（Property 5: 索引查询正确性）
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from findz.find.index import InvertedIndex, get_global_index, reset_global_index


# ==================== 属性测试 ====================

# 生成随机文件信息的策略
file_info_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
    'path': st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    'size': st.integers(min_value=0, max_value=10**9),
    'archive': st.text(max_size=30),
    'ext': st.sampled_from(['jpg', 'png', 'txt', 'py', 'zip', '', 'avif', 'mp4']),
})


@given(st.lists(file_info_strategy, min_size=1, max_size=100))
@settings(max_examples=100, deadline=None)
def test_index_query_correctness_archive(files):
    """
    Property 5: 索引查询正确性（archive 字段）
    
    *For any* 索引查询，通过索引查找的结果应该与全量扫描过滤的结果一致
    
    **Validates: Requirements 6.2, 6.3**
    """
    # 构建索引
    index = InvertedIndex.build_from_files(files)
    
    # 获取所有压缩包
    archives = index.get_archives()
    
    for archive in archives:
        # 索引查询
        indexed_result = index.filter_by_archive(files, archive)
        
        # 全量扫描
        full_scan_result = [
            f for f in files 
            if (f.get('archive', '') or f.get('container', '')) == archive
        ]
        
        # 验证结果一致
        assert len(indexed_result) == len(full_scan_result)
        for idx_file, scan_file in zip(indexed_result, full_scan_result):
            assert idx_file['path'] == scan_file['path']


@given(st.lists(file_info_strategy, min_size=1, max_size=100))
@settings(max_examples=100, deadline=None)
def test_index_query_correctness_ext(files):
    """
    Property 5: 索引查询正确性（ext 字段）
    
    *For any* 索引查询，通过索引查找的结果应该与全量扫描过滤的结果一致
    
    **Validates: Requirements 6.2, 6.3**
    """
    # 构建索引
    index = InvertedIndex.build_from_files(files)
    
    # 获取所有扩展名
    extensions = index.get_extensions()
    
    for ext in extensions:
        # 索引查询
        indexed_result = index.filter_by_ext(files, ext)
        
        # 全量扫描
        full_scan_result = [
            f for f in files 
            if f.get('ext', '').lower().lstrip('.') == ext.lower()
        ]
        
        # 验证结果一致
        assert len(indexed_result) == len(full_scan_result)


# ==================== 单元测试 ====================

def test_index_add_and_get():
    """测试添加和获取"""
    index = InvertedIndex()
    
    index.add(0, '/path/to/archive.zip', 'jpg')
    index.add(1, '/path/to/archive.zip', 'png')
    index.add(2, '/other/archive.zip', 'jpg')
    
    # 按压缩包查询
    assert index.get_by_archive('/path/to/archive.zip') == [0, 1]
    assert index.get_by_archive('/other/archive.zip') == [2]
    assert index.get_by_archive('/nonexistent') == []
    
    # 按扩展名查询
    assert index.get_by_ext('jpg') == [0, 2]
    assert index.get_by_ext('png') == [1]
    assert index.get_by_ext('gif') == []


def test_index_add_file():
    """测试从字典添加"""
    index = InvertedIndex()
    
    files = [
        {'path': '/a.jpg', 'archive': '/test.zip', 'ext': 'jpg'},
        {'path': '/b.png', 'archive': '/test.zip', 'ext': 'png'},
        {'path': '/c.txt', 'archive': '', 'ext': 'txt'},
    ]
    
    for idx, f in enumerate(files):
        index.add_file(idx, f)
    
    assert len(index.get_by_archive('/test.zip')) == 2
    assert len(index.get_by_ext('jpg')) == 1


def test_index_save_and_load():
    """测试保存和加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.json"
        
        # 创建并保存
        index = InvertedIndex()
        index.add(0, '/archive.zip', 'jpg')
        index.add(1, '/archive.zip', 'png')
        index.save(index_path)
        
        # 加载
        loaded = InvertedIndex.load(index_path)
        
        assert loaded is not None
        assert loaded.get_by_archive('/archive.zip') == [0, 1]
        assert loaded.get_by_ext('jpg') == [0]


def test_index_build_from_files():
    """测试从文件列表构建"""
    files = [
        {'path': '/a.jpg', 'archive': '/test.zip', 'ext': 'jpg'},
        {'path': '/b.jpg', 'archive': '/test.zip', 'ext': 'jpg'},
        {'path': '/c.png', 'archive': '/other.zip', 'ext': 'png'},
    ]
    
    index = InvertedIndex.build_from_files(files)
    
    assert index.count() == 3
    assert len(index.get_archives()) == 2
    assert len(index.get_extensions()) == 2


def test_index_filter():
    """测试过滤功能"""
    files = [
        {'path': '/a.jpg', 'archive': '/test.zip', 'ext': 'jpg'},
        {'path': '/b.png', 'archive': '/test.zip', 'ext': 'png'},
        {'path': '/c.jpg', 'archive': '/other.zip', 'ext': 'jpg'},
    ]
    
    index = InvertedIndex.build_from_files(files)
    
    # 按压缩包过滤
    result = index.filter_by_archive(files, '/test.zip')
    assert len(result) == 2
    assert result[0]['path'] == '/a.jpg'
    
    # 按扩展名过滤
    result = index.filter_by_ext(files, 'jpg')
    assert len(result) == 2


def test_index_clear():
    """测试清空"""
    index = InvertedIndex()
    index.add(0, '/archive.zip', 'jpg')
    
    index.clear()
    
    assert index.count() == 0
    assert index.get_by_archive('/archive.zip') == []


def test_global_index():
    """测试全局索引"""
    reset_global_index()
    
    index1 = get_global_index()
    index2 = get_global_index()
    
    assert index1 is index2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
