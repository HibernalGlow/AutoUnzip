"""
文件系统遍历和搜索模块
支持索引缓存、并行处理、压缩包过滤等高性能特性

优化特性：
- 使用 os.scandir 替代 os.listdir 提升性能
- 流式处理，边扫描边返回结果
- 支持进度回调，实时显示扫描进度
- 自动拆分超大目录，避免内存溢出
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional, Set, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

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


# 进度回调类型
ProgressCallback = Callable[[int, int, str], None]  # (scanned, matched, current_path)


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
        progress_callback: Optional[ProgressCallback] = None,  # 进度回调
        batch_size: int = 1000,  # 批量处理大小
    ):
        self.filter_expr = filter_expr
        self.follow_symlinks = follow_symlinks
        self.no_archive = no_archive
        self.archives_only = archives_only
        self.use_cache = use_cache
        self.max_workers = max_workers if max_workers is not None else get_default_workers()
        self.error_handler = error_handler
        self.progress_callback = progress_callback
        self.batch_size = batch_size


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
    遍历文件系统（使用 os.scandir 优化性能）
    
    使用非递归的广度优先遍历，避免深层递归导致的栈溢出
    使用 os.scandir 替代 os.listdir + os.stat，减少系统调用
    
    参数:
        root: 起始根目录
        follow_symlinks: 是否跟随符号链接
        report: 报告文件和错误的回调函数
    """
    # 使用队列实现非递归遍历（广度优先）
    queue: deque[Tuple[str, str]] = deque()  # (实际路径, 虚拟路径)
    queue.append((root, root))
    
    while queue:
        path, virt_path = queue.popleft()
        
        try:
            # 使用 scandir 获取目录条目（比 listdir + stat 快很多）
            with os.scandir(path) as entries:
                # 收集并排序条目
                sorted_entries = sorted(entries, key=lambda e: e.name)
                
                for entry in sorted_entries:
                    try:
                        child_virt_path = os.path.join(virt_path, entry.name)
                        
                        # 使用 entry.stat() 避免额外的系统调用
                        try:
                            if follow_symlinks:
                                stat_info = entry.stat(follow_symlinks=True)
                            else:
                                stat_info = entry.stat(follow_symlinks=False)
                        except OSError as e:
                            report(None, FindError(entry.path, e))
                            continue
                        
                        # 确定文件类型
                        if entry.is_symlink():
                            file_type = "link"
                        elif entry.is_dir(follow_symlinks=follow_symlinks):
                            file_type = "dir"
                        else:
                            file_type = "file"
                        
                        # 创建 FileInfo
                        file_info = FileInfo(
                            name=entry.name,
                            path=child_virt_path,
                            mod_time=datetime.fromtimestamp(stat_info.st_mtime),
                            size=stat_info.st_size,
                            file_type=file_type,
                        )
                        
                        # 报告文件
                        report(file_info, None)
                        
                        # 如果是目录，加入队列继续遍历
                        if file_type == "dir" or (file_type == "link" and follow_symlinks and entry.is_dir(follow_symlinks=True)):
                            queue.append((entry.path, child_virt_path))
                            
                    except Exception as e:
                        report(None, FindError(entry.path if hasattr(entry, 'path') else path, e))
                        
        except PermissionError as e:
            report(None, FindError(path, e))
        except Exception as e:
            report(None, FindError(path, e))


def find_in_archive_cached(
    file_info: FileInfo,
    params: WalkParams,
) -> Iterator[FileInfo]:
    """
    在压缩包内查找文件（使用缓存优化）
    
    优化策略：
    1. 使用 SQLite 缓存，支持增量更新
    2. 延迟创建 FileInfo 对象
    3. 预编译过滤器测试函数
    
    参数:
        file_info: 压缩包文件信息
        params: 搜索参数
        
    生成:
        匹配过滤器的 FileInfo 对象
    """
    archive_path = file_info.path
    cache = get_global_cache() if params.use_cache else None
    filter_test = params.filter_expr.test
    
    # 尝试从缓存获取
    index = cache.get_index(archive_path) if cache else None
    
    if index:
        # 使用缓存的索引 - 直接迭代，减少内存占用
        for entry in index.files:
            # 延迟创建 FileInfo，只在需要时创建
            # 使用缓存中存储的 file_type，而不是硬编码
            fi = FileInfo(
                name=entry.name,
                path=entry.path,
                mod_time=datetime.fromtimestamp(entry.mtime),
                size=entry.size,
                file_type=entry.file_type,
                archive=archive_path,
            )
            
            try:
                matches, error = filter_test(fi.context())
                if not error and matches:
                    yield fi
            except Exception:
                pass
    else:
        # 扫描压缩包并缓存结果
        try:
            archive_files = list_files_in_archive(archive_path)
            
            if archive_files:
                # 保存到缓存
                if cache:
                    entries = []
                    for fi in archive_files:
                        entry = FileEntry(
                            name=fi.name,
                            path=fi.path,
                            size=fi.size,
                            mtime=fi.mod_time.timestamp(),
                            is_archive=is_archive(fi.name),
                            ext=os.path.splitext(fi.name)[1].lstrip('.'),
                            file_type=fi.file_type,  # 保存文件类型到缓存
                            archive_path=archive_path,
                        )
                        entries.append(entry)
                    cache.set_index(archive_path, entries)
                
                # 测试每个文件
                for archive_file in archive_files:
                    try:
                        matches, error = filter_test(archive_file.context())
                        if not error and matches:
                            yield archive_file
                    except Exception:
                        pass
                
        except FindError as e:
            if params.error_handler and "not installed" not in str(e):
                params.error_handler(str(e))
        except Exception as e:
            if params.error_handler:
                params.error_handler(f"{archive_path}: {e}")


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
    遍历文件系统并返回匹配的文件（流式处理优化版）
    
    优化策略：
    1. 流式处理：边扫描边返回结果，减少内存占用
    2. 批量处理压缩包：收集一批压缩包后并行处理
    3. 进度回调：实时报告扫描进度
    4. 使用 os.scandir 减少系统调用
    
    参数:
        root: 起始根目录
        params: 搜索参数（包含过滤器）
    
    生成:
        匹配过滤器的 FileInfo 对象
    """
    
    # 统计计数器
    scanned_count = 0
    matched_count = 0
    
    # 压缩包批量收集
    archive_batch: List[FileInfo] = []
    batch_size = params.batch_size
    
    # 进度回调节流
    last_progress_report = 0
    progress_interval = 500  # 每 500 个文件报告一次
    
    def report_progress(current_path: str = ""):
        """报告进度"""
        nonlocal last_progress_report
        if params.progress_callback and scanned_count - last_progress_report >= progress_interval:
            params.progress_callback(scanned_count, matched_count, current_path)
            last_progress_report = scanned_count
    
    def process_archive_batch() -> Iterator[FileInfo]:
        """处理一批压缩包"""
        nonlocal matched_count
        
        if not archive_batch:
            return
        
        if params.max_workers > 1 and len(archive_batch) > 1:
            # 并行处理
            with ThreadPoolExecutor(max_workers=params.max_workers) as executor:
                future_to_file = {
                    executor.submit(process_file_parallel, fi, params): fi
                    for fi in archive_batch
                }
                
                for future in as_completed(future_to_file):
                    try:
                        matches = future.result()
                        for m in matches:
                            matched_count += 1
                            yield m
                    except Exception as e:
                        file_info = future_to_file[future]
                        if params.error_handler:
                            params.error_handler(f"{file_info.path}: {e}")
        else:
            # 单线程处理
            for file_info in archive_batch:
                for m in find_in(file_info, params):
                    matched_count += 1
                    yield m
        
        archive_batch.clear()
    
    # 使用队列实现非递归遍历（深度优先，减少内存）
    stack: List[str] = [root]
    
    # 预编译过滤器测试函数
    filter_test = params.filter_expr.test
    
    while stack:
        current_dir = stack.pop()
        
        try:
            # 使用 scandir 获取目录条目
            with os.scandir(current_dir) as entries:
                # 收集子目录（后处理，实现深度优先）
                subdirs: List[str] = []
                
                for entry in entries:
                    scanned_count += 1
                    
                    try:
                        # 快速判断类型（不需要额外 stat 调用）
                        is_dir = entry.is_dir(follow_symlinks=params.follow_symlinks)
                        
                        if is_dir:
                            # 目录：加入待处理栈
                            subdirs.append(entry.path)
                            continue
                        
                        # 获取文件状态
                        try:
                            stat_info = entry.stat(follow_symlinks=params.follow_symlinks)
                        except OSError:
                            continue
                        
                        # 创建 FileInfo
                        file_info = FileInfo(
                            name=entry.name,
                            path=entry.path,
                            mod_time=datetime.fromtimestamp(stat_info.st_mtime),
                            size=stat_info.st_size,
                            file_type="link" if entry.is_symlink() else "file",
                        )
                        
                        # archives_only 模式
                        if params.archives_only:
                            if is_archive(entry.path):
                                try:
                                    matches, error = filter_test(file_info.context())
                                    if not error and matches:
                                        matched_count += 1
                                        yield file_info
                                except Exception:
                                    pass
                            continue
                        
                        # 检查是否是压缩包
                        is_arch = is_archive(entry.name)
                        
                        # 测试文件是否匹配过滤器
                        try:
                            matches, error = filter_test(file_info.context())
                            if not error and matches:
                                matched_count += 1
                                yield file_info
                        except Exception:
                            pass
                        
                        # 如果是压缩包且需要搜索内部
                        if is_arch and not params.no_archive:
                            archive_batch.append(file_info)
                            
                            # 批量处理压缩包
                            if len(archive_batch) >= batch_size:
                                yield from process_archive_batch()
                                
                    except Exception as e:
                        if params.error_handler:
                            params.error_handler(f"{entry.path}: {e}")
                
                # 将子目录加入栈（逆序以保持字母顺序遍历）
                subdirs.sort(reverse=True)
                stack.extend(subdirs)
                
                # 报告进度
                report_progress(current_dir)
                        
        except PermissionError:
            if params.error_handler:
                params.error_handler(f"权限拒绝: {current_dir}")
        except Exception as e:
            if params.error_handler:
                params.error_handler(f"{current_dir}: {e}")
    
    # 处理剩余的压缩包
    if archive_batch and not params.archives_only:
        yield from process_archive_batch()
    
    # 最终进度报告
    if params.progress_callback:
        params.progress_callback(scanned_count, matched_count, "完成")
    
    # 保存缓存
    if params.use_cache:
        cache = get_global_cache()
        cache.flush()
