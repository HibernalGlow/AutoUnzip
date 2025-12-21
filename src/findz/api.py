"""
findz 核心 API 模块

提供无 CLI 依赖的搜索、分组、筛选功能
可作为库独立使用
"""

import os
import re
from datetime import datetime
from typing import Iterator, List, Dict, Any, Optional, Callable

from .filter.filter import create_filter
from .filter.size import format_size, parse_size
from .find.find import FileInfo
from .find.walk import WalkParams, walk
from .find.cache import CacheManager, get_cache_manager
from .find.index import InvertedIndex


def file_info_to_dict(file_info: FileInfo) -> Dict[str, Any]:
    """将 FileInfo 转换为字典"""
    return {
        'name': file_info.name,
        'path': file_info.path,
        'size': file_info.size,
        'size_formatted': format_size(file_info.size),
        'mod_time': file_info.mod_time.isoformat(),
        'date': file_info.mod_time.strftime("%Y-%m-%d"),
        'time': file_info.mod_time.strftime("%H:%M:%S"),
        'type': file_info.file_type,
        'container': file_info.container or '',
        'archive': file_info.archive or '',
        'ext': os.path.splitext(file_info.name)[1].lstrip('.').lower(),
    }


def search(
    paths: List[str],
    where: str = "1",
    follow_symlinks: bool = False,
    no_archive: bool = False,
    archives_only: bool = False,
    workers: int = 4,
    use_cache: bool = True,
    error_handler: Optional[Callable[[str], None]] = None,
) -> Iterator[FileInfo]:
    """
    搜索文件，返回匹配结果的迭代器（流式）
    
    Args:
        paths: 搜索路径列表
        where: SQL-like 过滤表达式
        follow_symlinks: 是否跟随符号链接
        no_archive: 是否禁用压缩包搜索
        archives_only: 是否只返回压缩包本身
        workers: 并行工作线程数
        use_cache: 是否使用缓存
        error_handler: 错误处理回调
        
    Yields:
        匹配的 FileInfo 对象
    """
    # 创建过滤器
    filter_expr = create_filter(where)
    
    # 遍历参数
    params = WalkParams(
        filter_expr=filter_expr,
        follow_symlinks=follow_symlinks,
        no_archive=no_archive,
        archives_only=archives_only,
        use_cache=use_cache,
        max_workers=workers,
        error_handler=error_handler,
    )
    
    # 遍历所有路径
    for path in paths:
        yield from walk(path, params)


def search_cached(
    paths: List[str],
    where: str = "1",
    follow_symlinks: bool = False,
    no_archive: bool = False,
    archives_only: bool = False,
    workers: int = 4,
    use_cache: bool = True,
    error_handler: Optional[Callable[[str], None]] = None,
    cache_manager: Optional[CacheManager] = None,
) -> List[Dict[str, Any]]:
    """
    搜索文件并缓存结果
    
    Args:
        paths: 搜索路径列表
        where: SQL-like 过滤表达式
        其他参数同 search()
        cache_manager: 缓存管理器（可选）
        
    Returns:
        搜索结果列表（字典格式）
    """
    # 收集结果
    results = []
    for file_info in search(
        paths=paths,
        where=where,
        follow_symlinks=follow_symlinks,
        no_archive=no_archive,
        archives_only=archives_only,
        workers=workers,
        use_cache=use_cache,
        error_handler=error_handler,
    ):
        results.append(file_info_to_dict(file_info))
    
    # 保存到缓存
    cache = cache_manager or get_cache_manager()
    cache.save_results(results, metadata={
        'where': where,
        'paths': paths,
        'archives_only': archives_only,
    })
    
    return results


def load_cache(
    cache_manager: Optional[CacheManager] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    加载上次搜索结果缓存
    
    Args:
        cache_manager: 缓存管理器（可选）
        
    Returns:
        缓存的文件列表，不存在返回 None
    """
    cache = cache_manager or get_cache_manager()
    data = cache.load_results()
    if data is None:
        return None
    return data.get('files', [])


def group_by(
    files: List[Dict[str, Any]],
    field: str,
) -> List[Dict[str, Any]]:
    """
    按字段分组统计
    
    Args:
        files: 文件列表
        field: 分组字段 ('archive' | 'ext' | 'dir')
        
    Returns:
        分组统计列表，每项包含:
        - key: 分组键
        - name: 显示名称
        - count: 文件数量
        - total_size: 总大小
        - avg_size: 平均大小
        - files: 该组的文件列表
    """
    groups: Dict[str, Dict] = {}
    
    for f in files:
        # 确定分组键
        if field == 'archive':
            key = f.get('archive') or f.get('container') or ''
            if not key:
                continue  # 跳过不在压缩包内的文件
        elif field == 'ext':
            key = f.get('ext', '') or '(无扩展名)'
        elif field == 'dir':
            full_path = f.get('container', '')
            if full_path:
                full_path += '//' + f.get('path', '')
            else:
                full_path = f.get('path', '')
            parts = re.split(r'[/\\]|//', full_path)
            key = '/'.join(parts[:-1]) if len(parts) > 1 else '(根目录)'
        else:
            key = str(f.get(field, ''))
        
        if key not in groups:
            groups[key] = {
                'key': key,
                'name': key.split('/')[-1] if '/' in key else key,
                'count': 0,
                'total_size': 0,
                'files': [],
            }
        
        groups[key]['count'] += 1
        groups[key]['total_size'] += f.get('size', 0)
        groups[key]['files'].append(f)
    
    # 计算平均大小
    result = []
    for g in groups.values():
        g['avg_size'] = g['total_size'] / g['count'] if g['count'] > 0 else 0
        g['avg_size_formatted'] = format_size(int(g['avg_size']))
        g['total_size_formatted'] = format_size(g['total_size'])
        result.append(g)
    
    return result


def parse_refine_filter(filter_str: str) -> Dict[str, Any]:
    """
    解析二次筛选表达式
    
    支持的格式:
    - count > 10
    - avg_size > 1M
    - total_size < 100M
    - name like test%
    
    Args:
        filter_str: 筛选表达式
        
    Returns:
        解析后的条件字典
    """
    filter_str = filter_str.strip()
    result = {}
    
    # 解析多个条件（用 AND 分隔）
    conditions = re.split(r'\s+AND\s+', filter_str, flags=re.IGNORECASE)
    
    for cond in conditions:
        cond = cond.strip()
        
        # 匹配: field op value
        match = re.match(r'(\w+)\s*(>=|<=|!=|<>|>|<|=|LIKE|RLIKE)\s*(.+)', cond, re.IGNORECASE)
        if match:
            field, op, value = match.groups()
            field = field.lower()
            op = op.upper()
            value = value.strip().strip('"\'')
            
            # 解析大小值
            if field in ('avg_size', 'total_size', 'size'):
                try:
                    value = parse_size(value)
                except:
                    pass
            elif field == 'count':
                try:
                    value = int(value)
                except:
                    pass
            
            result[field] = {'op': op, 'value': value}
    
    return result


def apply_refine_filter(
    groups: List[Dict],
    filter_dict: Dict[str, Any]
) -> List[Dict]:
    """
    应用二次筛选条件到分组结果
    
    Args:
        groups: 分组列表
        filter_dict: 解析后的筛选条件
        
    Returns:
        过滤后的分组列表
    """
    def match_condition(item: Dict, field: str, op: str, value: Any) -> bool:
        item_value = item.get(field)
        if item_value is None:
            return False
        
        if op == '=':
            return str(item_value).lower() == str(value).lower()
        elif op in ('!=', '<>'):
            return str(item_value).lower() != str(value).lower()
        elif op == '>':
            return item_value > value
        elif op == '<':
            return item_value < value
        elif op == '>=':
            return item_value >= value
        elif op == '<=':
            return item_value <= value
        elif op == 'LIKE':
            pattern = value.replace('%', '.*').replace('_', '.')
            return bool(re.match(pattern, str(item_value), re.IGNORECASE))
        elif op == 'RLIKE':
            return bool(re.search(value, str(item_value), re.IGNORECASE))
        return True
    
    filtered = []
    for group in groups:
        match = True
        for field, cond in filter_dict.items():
            if not match_condition(group, field, cond['op'], cond['value']):
                match = False
                break
        if match:
            filtered.append(group)
    
    return filtered


def refine(
    groups: List[Dict[str, Any]],
    filter_expr: str,
) -> List[Dict[str, Any]]:
    """
    二次筛选分组结果
    
    Args:
        groups: 分组列表
        filter_expr: 筛选表达式，如 'avg_size > 1M'
        
    Returns:
        过滤后的分组列表
    """
    filter_dict = parse_refine_filter(filter_expr)
    return apply_refine_filter(groups, filter_dict)


def sort_groups(
    groups: List[Dict[str, Any]],
    sort_by: str = 'avg_size',
    descending: bool = True,
) -> List[Dict[str, Any]]:
    """
    排序分组结果
    
    Args:
        groups: 分组列表
        sort_by: 排序字段 (name/count/total_size/avg_size)
        descending: 是否降序
        
    Returns:
        排序后的分组列表
    """
    if sort_by in ('name', 'count', 'total_size', 'avg_size'):
        groups.sort(key=lambda x: x.get(sort_by, 0), reverse=descending)
    return groups


def clear_cache(cache_manager: Optional[CacheManager] = None) -> None:
    """
    清空所有缓存
    
    Args:
        cache_manager: 缓存管理器（可选）
    """
    cache = cache_manager or get_cache_manager()
    cache.clear()


def search_nested_archives(
    paths: List[str],
    error_handler: Optional[Callable[[str], None]] = None,
) -> List[str]:
    """
    搜索包含嵌套压缩包的外层压缩包
    
    Args:
        paths: 搜索路径列表
        error_handler: 错误处理回调
        
    Returns:
        包含嵌套压缩包的外层压缩包路径列表（已排序去重）
    """
    from .find.walk import is_archive
    
    nested_containers = set()
    
    # 搜索所有文件
    for file_info in search(
        paths=paths,
        where="1",  # 匹配所有文件
        follow_symlinks=False,
        no_archive=False,  # 必须扫描压缩包内部
        error_handler=error_handler,
    ):
        # 检查是否在压缩包内（archive 不为空）
        if file_info.archive:
            # 检查文件本身是否是压缩包
            if is_archive(file_info.name):
                nested_containers.add(file_info.archive)
    
    return sorted(nested_containers)


def get_unique_archives(files: List[FileInfo]) -> List[str]:
    """
    从文件列表中提取唯一的压缩包路径
    
    Args:
        files: FileInfo 列表
        
    Returns:
        唯一的压缩包路径列表（保持顺序）
    """
    archives = [f.archive for f in files if getattr(f, "archive", None)]
    return list(dict.fromkeys(archives))
