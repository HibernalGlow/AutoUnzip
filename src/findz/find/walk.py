"""
文件系统遍历和搜索模块
支持索引缓存、并行处理、压缩包过滤等高性能特性
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..filter.filter import FilterExpression
from .find import FileInfo, FindError, list_files_in_archive
from .index_cache import get_global_cache, FileEntry
from .cache import get_cache_manager


def get_default_workers() -> int:
    """获取默认并行工作线程数：min(cpu_count, 4)"""
    try:
        cpu_count = os.cpu_count() or 1
        return min(cpu_count, 4)
    except:
        return 4


class WalkParams:
    """文件系统遍历参数"""
    
    def __init__(
        self,
        filter_expr: FilterExpression,
        follow_symlinks: bool = False,
        no_archive: bool = False,
        archives_only: bool = False,  # 只输出压缩包本身
        use_cache: bool = True,  # 是否使用索引缓存
        max_workers: int = None,  # 并行处理线程数，None 表示使用默认值
        error_handler: Optional[Callable[[str], None]] = None,
    ):
        self.filter_expr = filter_expr
        self.follow_symlinks = follow_symlinks
        self.no_archive = no_archive
        self.archives_only = archives_only
        self.use_cache = use_cache
        self.max_workers = max_workers if max_workers is not None else get_default_workers()
        self.error_handler = error_handler


# 支持的压缩包扩展名
ARCHIVE_EXTENSIONS = {'.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', 
                      '.tgz', '.tbz2', '.txz', '.tar.gz', '.tar.bz2', '.tar.xz'}


def is_archive(path: str) -> bool:
    """判断文件是否为压缩包"""
    lower_path = path.lower()
    return any(lower_path.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def make_file_info(fullpath: str, stat_info: os.stat_result) -> FileInfo:
    """
    从 os.stat 结果创建 FileInfo 对象
    
    参数:
        fullpath: 文件完整路径
        stat_info: os.stat 返回的状态信息
        
    返回:
        FileInfo 对象
    """
    
    # 确定文件类型
    if os.path.islink(fullpath):
        file_type = "link"
    elif os.path.isdir(fullpath):
        file_type = "dir"
    else:
        file_type = "file"
    
    return FileInfo(
        name=os.path.basename(fullpath),
        path=fullpath,
        mod_time=datetime.fromtimestamp(stat_info.st_mtime),
        size=stat_info.st_size,
        file_type=file_type,
    )


def fs_walk(
    root: str,
    follow_symlinks: bool,
    report: Callable[[Optional[FileInfo], Optional[Exception]], None],
) -> None:
    """
    遍历文件系统
    
    参数:
        root: 起始根目录
        follow_symlinks: 是否跟随符号链接
        report: 报告文件和错误的回调函数
    """
    
    def walk_recursive(path: str, virt_path: str) -> None:
        """递归遍历目录"""
        
        try:
            # 使用 lstat 不自动跟随符号链接
            stat_info = os.lstat(path)
        except Exception as e:
            report(None, FindError(path, e))
            return
        
        # 创建 FileInfo
        file_info = make_file_info(virt_path, stat_info)
        
        # 处理符号链接
        if file_info.file_type == "link" and follow_symlinks:
            try:
                # 解析符号链接
                real_path = os.path.realpath(path)
                stat_info = os.stat(real_path)
                
                # 使用解析后的信息但保留原始路径
                file_info2 = make_file_info(real_path, stat_info)
                file_info = FileInfo(
                    name=file_info.name,
                    path=file_info.path,
                    mod_time=file_info2.mod_time,
                    size=file_info2.size,
                    file_type=file_info2.file_type,
                )
                
                # 更新路径用于递归
                path = real_path
            except Exception as e:
                report(None, FindError(path, e))
                return
        
        # 报告文件/目录
        report(file_info, None)
        
        # 如果是目录，递归进入
        if file_info.is_dir():
            try:
                entries = sorted(os.listdir(path))
            except Exception as e:
                report(None, FindError(path, e))
                return
            
            for entry in entries:
                child_path = os.path.join(path, entry)
                child_virt_path = os.path.join(virt_path, entry)
                walk_recursive(child_path, child_virt_path)
    
    walk_recursive(root, root)


def find_in_archive_cached(
    file_info: FileInfo,
    params: WalkParams,
) -> Iterator[FileInfo]:
    """
    在压缩包内查找文件（使用缓存优化）
    
    参数:
        file_info: 压缩包文件信息
        params: 搜索参数
        
    生成:
        匹配过滤器的 FileInfo 对象
    """
    archive_path = file_info.path
    cache = get_global_cache() if params.use_cache else None
    
    # 尝试从缓存获取
    index = cache.get_index(archive_path) if cache else None
    
    if index:
        # 使用缓存的索引
        archive_files = []
        for entry in index.files:
            # 从缓存条目重建 FileInfo
            fi = FileInfo(
                name=entry.name,
                path=entry.path,
                mod_time=datetime.fromtimestamp(entry.mtime),
                size=entry.size,
                file_type="file",
                archive=archive_path,
            )
            archive_files.append(fi)
    else:
        # 扫描压缩包并缓存结果
        try:
            archive_files = list_files_in_archive(archive_path)
            
            if archive_files and cache:
                # 保存到缓存
                entries = []
                for fi in archive_files:
                    entry = FileEntry(
                        name=fi.name,
                        path=fi.path,
                        size=fi.size,
                        mtime=fi.mod_time.timestamp(),
                        is_archive=is_archive(fi.name),
                        ext=os.path.splitext(fi.name)[1].lstrip('.'),
                        archive_path=archive_path,
                    )
                    entries.append(entry)
                cache.set_index(archive_path, entries)
                
        except FindError as e:
            # 不是压缩包或读取错误
            if params.error_handler and "not installed" not in str(e):
                params.error_handler(str(e))
            return
        except Exception as e:
            if params.error_handler:
                params.error_handler(f"{archive_path}: {e}")
            return
    
    # 对压缩包内文件排序
    if archive_files:
        archive_files.sort(key=lambda f: f.path)
        
        # 测试每个文件是否匹配
        for archive_file in archive_files:
            try:
                matches, error = params.filter_expr.test(archive_file.context())
                if error:
                    if params.error_handler:
                        params.error_handler(str(error))
                elif matches:
                    yield archive_file
            except Exception as e:
                if params.error_handler:
                    params.error_handler(f"{archive_file.path}: {e}")


def find_in(file_info: FileInfo, params: WalkParams) -> Iterator[FileInfo]:
    """
    查找匹配过滤器的文件（包括压缩包内）
    
    参数:
        file_info: 要搜索的文件
        params: 搜索参数
    
    生成:
        匹配过滤器的 FileInfo 对象
    """
    
    # 如果是 archives_only 模式，只处理压缩包文件本身
    if params.archives_only:
        # 只对压缩包文件进行过滤测试
        if is_archive(file_info.path):
            try:
                matches, error = params.filter_expr.test(file_info.context())
                if error:
                    if params.error_handler:
                        params.error_handler(str(error))
                elif matches:
                    yield file_info
            except Exception as e:
                if params.error_handler:
                    params.error_handler(f"{file_info.path}: {e}")
        return  # 不进入压缩包内部
    
    # 正常模式：测试文件本身是否匹配
    try:
        matches, error = params.filter_expr.test(file_info.context())
        if error:
            if params.error_handler:
                params.error_handler(str(error))
        elif matches:
            yield file_info
    except Exception as e:
        if params.error_handler:
            params.error_handler(f"{file_info.path}: {e}")
    
    # 如果是目录或禁用压缩包搜索，停止
    if file_info.is_dir() or params.no_archive:
        return
    
    # 搜索压缩包内部（使用缓存）
    if is_archive(file_info.path):
        yield from find_in_archive_cached(file_info, params)


def process_file_parallel(
    file_info: FileInfo,
    params: WalkParams,
) -> list[FileInfo]:
    """
    并行处理单个文件（用于线程池）
    
    参数:
        file_info: 文件信息
        params: 搜索参数
        
    返回:
        匹配的文件列表
    """
    return list(find_in(file_info, params))


def walk(
    root: str,
    params: WalkParams,
) -> Iterator[FileInfo]:
    """
    遍历文件系统并返回匹配的文件
    
    参数:
        root: 起始根目录
        params: 搜索参数（包含过滤器）
    
    生成:
        匹配过滤器的 FileInfo 对象
    """
    
    collected_files = []  # 收集所有文件
    archive_files = []  # 压缩包文件单独收集
    
    def report(file_info: Optional[FileInfo], error: Optional[Exception]) -> None:
        """处理 fs_walk 返回的文件或错误"""
        if error:
            if params.error_handler:
                params.error_handler(str(error))
        elif file_info:
            # 区分压缩包和普通文件
            if is_archive(file_info.path):
                archive_files.append(file_info)
            else:
                collected_files.append(file_info)
    
    # 开始遍历文件系统
    fs_walk(root, params.follow_symlinks, report)
    
    # 如果是 archives_only 模式，只处理压缩包
    if params.archives_only:
        # 只处理压缩包文件
        for file_info in archive_files:
            try:
                matches, error = params.filter_expr.test(file_info.context())
                if error:
                    if params.error_handler:
                        params.error_handler(str(error))
                elif matches:
                    yield file_info
            except Exception as e:
                if params.error_handler:
                    params.error_handler(f"{file_info.path}: {e}")
        
        # 保存缓存并返回（不继续处理）
        if params.use_cache:
            cache = get_global_cache()
            cache.flush()
        return
    
    # 先处理非压缩包文件（快速）
    for file_info in collected_files:
        if file_info.is_dir():
            continue
        try:
            matches, error = params.filter_expr.test(file_info.context())
            if error:
                if params.error_handler:
                    params.error_handler(str(error))
            elif matches:
                yield file_info
        except Exception as e:
            if params.error_handler:
                params.error_handler(f"{file_info.path}: {e}")
    
    # 并行处理压缩包文件（可能很慢）
    if archive_files:
        if params.max_workers > 1:
            # 使用线程池并行处理
            with ThreadPoolExecutor(max_workers=params.max_workers) as executor:
                # 提交所有任务
                future_to_file = {
                    executor.submit(process_file_parallel, fi, params): fi
                    for fi in archive_files
                }
                
                # 收集结果
                for future in as_completed(future_to_file):
                    try:
                        matches = future.result()
                        yield from matches
                    except Exception as e:
                        file_info = future_to_file[future]
                        if params.error_handler:
                            params.error_handler(f"{file_info.path}: {e}")
        else:
            # 单线程顺序处理
            for file_info in archive_files:
                yield from find_in(file_info, params)
    
    # 保存缓存
    if params.use_cache:
        cache = get_global_cache()
        cache.flush()
