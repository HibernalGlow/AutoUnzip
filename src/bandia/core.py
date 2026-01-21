"""
bandia 核心业务逻辑
解压和压缩的核心函数，供 CLI 和 API 调用
"""

import subprocess
import time
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from send2trash import send2trash
from rich.console import Console
from rich.progress import (
    Progress, TextColumn, BarColumn, SpinnerColumn,
    TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn
)

from .types import (
    ExtractResult, BatchExtractResult,
    CompressResult, BatchCompressResult, PathMapping, ExtractMode
)
from .utils import (
    find_bz_executable, filter_archives, get_shutdown_event, 
    reset_shutdown_event, ProgressCallback, DEFAULT_PARALLEL_WORKERS
)

# Windows encoding fix
import sys
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


# ============ 输出路径计算 ============

def get_output_path(archive: Path, bz_path: Path) -> Optional[Path]:
    """
    计算 Bandizip -target:auto 的实际输出目录
    
    Bandizip 的 -target:auto 行为:
    - 如果压缩包内只有一个根目录，则解压到同级目录（即那个根目录）
    - 如果压缩包内有多个文件/目录，则创建与压缩包同名的目录
    """
    try:
        cmd = [str(bz_path), "l", str(archive)]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        if proc.returncode != 0:
            logger.debug(f"列出压缩包内容失败: {archive}")
            return None
        
        lines = proc.stdout.strip().split('\n')
        root_items = set()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('-') or line.startswith('Date') or line.startswith('Attr'):
                continue
            
            parts = line.split()
            if len(parts) >= 5:
                path_part = ' '.join(parts[4:])
                root = path_part.split('/')[0].split('\\')[0]
                if root:
                    root_items.add(root)
        
        parent_dir = archive.parent
        archive_stem = archive.stem
        
        if len(root_items) == 1:
            single_root = list(root_items)[0]
            output = parent_dir / single_root
        else:
            output = parent_dir / archive_stem
        
        return output
        
    except Exception as e:
        logger.debug(f"计算输出路径失败 {archive}: {e}")
        return None


# ============ 解压功能 ============

def extract_single(
    archive: Path,
    bz_path: Path,
    delete: bool = True,
    use_trash: bool = True,
    overwrite_mode: str = "overwrite",
    extract_mode: ExtractMode = ExtractMode.AUTO,
    output_prefix: str = "【a】"
) -> ExtractResult:
    """解压单个压缩包
    
    Args:
        archive: 压缩包路径
        bz_path: Bandizip 可执行文件路径
        delete: 解压后删除源文件
        use_trash: 使用回收站
        overwrite_mode: 冲突处理模式 (overwrite/skip/rename)
        extract_mode: 解压模式 (auto/normal)
        output_prefix: 普通模式输出前缀 (默认 "【a】")
    """
    shutdown_event = get_shutdown_event()
    
    if shutdown_event.is_set():
        return ExtractResult(archive, False, error="用户中断")
    
    if not archive.exists():
        return ExtractResult(archive, False, error="文件不存在")
    
    if archive.is_dir():
        return ExtractResult(archive, False, error="是目录")
    
    try:
        file_size = archive.stat().st_size
    except Exception:
        file_size = 0
    
    mode_flags = {"overwrite": "-aoa", "skip": "-aos", "rename": "-aou"}
    conflict_flag = mode_flags.get(overwrite_mode, "-aoa")
    
    # 根据解压模式构建命令
    if extract_mode == ExtractMode.AUTO:
        # 智能解压
        output_path = get_output_path(archive, bz_path)
        cmd = [str(bz_path), "x", "-y", conflict_flag, "-target:auto", str(archive)]
    else:
        # 普通解压 - 到【前缀】压缩包名 目录
        target_dir = archive.parent / f"{output_prefix}{archive.stem}"
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir
        cmd = [str(bz_path), "x", "-y", conflict_flag, f"-o:{target_dir}", str(archive)]
    
    start_time = time.time()
    
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        return ExtractResult(archive, False, error=str(e))
    
    duration = time.time() - start_time
    
    if proc.returncode != 0:
        error_msg = proc.stderr or proc.stdout or f"返回码 {proc.returncode}"
        return ExtractResult(archive, False, duration, file_size, error_msg[:200])
    
    if delete:
        try:
            if use_trash:
                send2trash(str(archive))
            else:
                archive.unlink()
        except Exception as e:
            logger.warning(f"删除失败 {archive.name}: {e}")
    
    return ExtractResult(archive, True, duration, file_size, "", output_path)


def extract_batch(
    paths: List[Path],
    delete: bool = True,
    use_trash: bool = True,
    overwrite_mode: str = "overwrite",
    callback: Optional[ProgressCallback] = None,
    parallel: bool = False,
    workers: Optional[int] = None,
    extract_mode: ExtractMode = ExtractMode.AUTO,
    output_prefix: str = "【a】"
) -> BatchExtractResult:
    """批量解压压缩包
    
    Args:
        paths: 压缩包路径列表
        delete: 解压后删除源文件
        use_trash: 使用回收站
        overwrite_mode: 冲突处理模式
        callback: 进度回调
        parallel: 是否并行解压
        workers: 并行工作线程数
        extract_mode: 解压模式 (auto/normal)
        output_prefix: 普通模式输出前缀
    """
    reset_shutdown_event()
    
    bz_path = find_bz_executable()
    if not bz_path:
        return BatchExtractResult(
            success=False,
            message="未找到 Bandizip (bz.exe)，请安装或设置环境变量 BANDIZIP_PATH"
        )
    
    if callback:
        callback.log(f"使用 Bandizip: {bz_path}")
        mode_desc = "智能解压" if extract_mode == ExtractMode.AUTO else f"普通解压 (前缀: {output_prefix})"
        callback.log(f"解压模式: {mode_desc}")
    
    paths = filter_archives(paths)
    if not paths:
        return BatchExtractResult(success=False, message="没有有效的压缩包路径")
    
    total = len(paths)
    
    if callback:
        callback.log(f"开始解压 {total} 个压缩包...")
        callback.progress(0, f"准备解压 {total} 个文件")
    
    if parallel and total > 1:
        results = _extract_parallel(
            paths, bz_path, delete, use_trash, overwrite_mode,
            workers or DEFAULT_PARALLEL_WORKERS, callback,
            extract_mode, output_prefix
        )
    else:
        results = _extract_sequential(
            paths, bz_path, delete, use_trash, overwrite_mode, callback,
            extract_mode, output_prefix
        )
    
    extracted = sum(1 for r in results if r.success)
    failed = len(results) - extracted
    
    success = failed == 0
    message = f"解压完成: {extracted} 成功, {failed} 失败"
    
    if callback:
        callback.progress(100, "解压完成")
        callback.log(f"📊 {message}")
    
    return BatchExtractResult(
        success=success,
        message=message,
        extracted=extracted,
        failed=failed,
        total=total,
        results=results
    )


def _extract_sequential(
    paths: List[Path],
    bz_path: Path,
    delete: bool,
    use_trash: bool,
    overwrite_mode: str,
    callback: Optional[ProgressCallback],
    extract_mode: ExtractMode = ExtractMode.AUTO,
    output_prefix: str = "【a】"
) -> List[ExtractResult]:
    """串行解压"""
    results: List[ExtractResult] = []
    total = len(paths)
    shutdown_event = get_shutdown_event()
    
    # Check if we can support unicode
    use_unicode = True
    try:
        if sys.platform == "win32":
            # On Windows, checked if we successfully reconfigured to utf-8
            use_unicode = getattr(sys.stdout, "encoding", "").lower().replace("-", "") == "utf8"
    except Exception:
        use_unicode = False

    with Progress(
        SpinnerColumn(spinner_name="dots" if use_unicode else "simpleDots"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        main_task = progress.add_task(f"[cyan]解压进度: 0/{total}", total=total)
        
        for idx, archive in enumerate(paths):
            if shutdown_event.is_set():
                progress.console.print("[yellow]已取消剩余任务[/yellow]")
                break
            
            display_name = archive.name[:40] + "..." if len(archive.name) > 40 else archive.name
            progress.update(main_task, description=f"[cyan]解压: {display_name}")
            
            if callback:
                progress_pct = int(5 + (idx / total) * 90)
                callback.progress(progress_pct, f"STARTED:{idx}", archive.name)
                callback.progress(progress_pct, f"解压 {idx + 1}/{total}", archive.name)
            
            result = extract_single(
                archive, bz_path, delete, use_trash, overwrite_mode,
                extract_mode, output_prefix
            )
            results.append(result)
            
            if result.success:
                size_mb = result.file_size / 1024 / 1024
                progress.console.print(
                    f"  [green]✓[/green] {display_name} | "
                    f"{size_mb:.1f}MB ({result.duration:.2f}s)"
                )
                if callback:
                    callback.log(f"✅ 成功 ({result.duration:.2f}s): {archive.name}")
            else:
                err_msg = result.error[:50] if result.error else "未知错误"
                progress.console.print(f"  [red]✗[/red] {display_name} | {err_msg}")
                if callback:
                    callback.log(f"❌ 失败: {archive.name} - {result.error}")
            
            progress.update(main_task, completed=idx + 1,
                           description=f"[cyan]解压进度: {idx + 1}/{total}")
    
    return results


def _extract_parallel(
    paths: List[Path],
    bz_path: Path,
    delete: bool,
    use_trash: bool,
    overwrite_mode: str,
    workers: int,
    callback: Optional[ProgressCallback],
    extract_mode: ExtractMode = ExtractMode.AUTO,
    output_prefix: str = "【a】"
) -> List[ExtractResult]:
    """并行解压"""
    results: List[ExtractResult] = []
    total = len(paths)
    completed = 0
    shutdown_event = get_shutdown_event()
    
    console.print(f"[cyan]⚡ 并行解压模式: {workers} 个工作线程[/cyan]")
    
    # Check if we can support unicode
    use_unicode = True
    try:
        if sys.platform == "win32":
            use_unicode = getattr(sys.stdout, "encoding", "").lower().replace("-", "") == "utf8"
    except Exception:
        use_unicode = False

    with Progress(
        SpinnerColumn(spinner_name="dots" if use_unicode else "simpleDots"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        main_task = progress.add_task(f"[cyan]并行解压: 0/{total}", total=total)
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for idx, archive in enumerate(paths):
                if callback:
                    progress_pct = int(5 + (completed / total) * 90)
                    callback.progress(progress_pct, f"STARTED:{idx}", archive.name)
                
                future = executor.submit(
                    extract_single, archive, bz_path, delete, use_trash, overwrite_mode,
                    extract_mode, output_prefix
                )
                futures[future] = (idx, archive)
            
            for future in as_completed(futures):
                if shutdown_event.is_set():
                    for f in futures:
                        f.cancel()
                    progress.console.print("[yellow]已取消剩余任务[/yellow]")
                    break
                
                idx, archive = futures[future]
                try:
                    result = future.result(timeout=0.1)
                    results.append(result)
                    completed += 1
                    
                    if callback:
                        progress_pct = int(5 + (completed / total) * 90)
                        callback.progress(progress_pct, f"FINISHED:{idx}|解压 {completed}/{total}", archive.name)
                    
                    display_name = archive.name[:40] + "..." if len(archive.name) > 40 else archive.name
                    if result.success:
                        size_mb = result.file_size / 1024 / 1024
                        progress.console.print(
                            f"  [green]✓[/green] {display_name} | "
                            f"{size_mb:.1f}MB ({result.duration:.2f}s)"
                        )
                        if callback:
                            callback.log(f"✅ 成功 ({result.duration:.2f}s): {archive.name}")
                    else:
                        err_msg = result.error[:50] if result.error else "未知错误"
                        progress.console.print(f"  [red]✗[/red] {display_name} | {err_msg}")
                        if callback:
                            callback.log(f"❌ 失败: {archive.name} - {result.error}")
                    
                    progress.update(main_task, completed=completed,
                                   description=f"[cyan]并行解压: {completed}/{total}")
                except TimeoutError:
                    continue
                except Exception as e:
                    completed += 1
                    results.append(ExtractResult(archive, False, error=str(e)))
                    progress.update(main_task, completed=completed)
    
    return results


# ============ 压缩功能 ============

def compress_single(
    source: Path,
    archive_path: Path,
    bz_path: Path,
    delete_source: bool = True,
    format: str = "zip"
) -> CompressResult:
    """压缩单个目录/文件"""
    shutdown_event = get_shutdown_event()
    
    if shutdown_event.is_set():
        return CompressResult(source, archive_path, False, error="用户中断")
    
    if not source.exists():
        return CompressResult(source, archive_path, False, error="源路径不存在")
    
    # 确保输出目录存在
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 构建压缩命令 - 使用相对路径以避免某些版本 Bandizip 对长路径或特殊字符的解析错误
    # 注意: 不使用 -sdel，因为某些版本 Bandizip 会报 Parameter Parsing Error
    cwd = source.parent
    archive_name = archive_path.name
    source_name = source.name
    
    cmd = [str(bz_path), "a", "-y", archive_name, source_name]
    
    start_time = time.time()
    
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd
        )
    except Exception as e:
        return CompressResult(source, archive_path, False, error=str(e))
    
    duration = time.time() - start_time
    
    if proc.returncode != 0:
        error_msg = (proc.stderr or proc.stdout or f"返回码 {proc.returncode}").strip()
        # 如果长度太长，保留末尾部分，因为错误通常在末尾
        if len(error_msg) > 500:
            error_msg = "..." + error_msg[-497:]
        return CompressResult(source, archive_path, False, duration, error_msg)
    
    # 压缩成功后手动删除源文件
    if delete_source:
        try:
            # 优先使用回收站
            send2trash(str(source))
        except Exception as e:
            logger.warning(f"删除源文件失败 (尝试 send2trash): {e}")
            try:
                if source.is_dir():
                    import shutil
                    shutil.rmtree(source)
                else:
                    source.unlink()
            except Exception as e2:
                logger.error(f"删除源文件失败 (物理删除): {e2}")
    
    return CompressResult(source, archive_path, True, duration)


def compress_batch(
    mappings: List[PathMapping],
    delete_source: bool = True,
    format: str = "zip",
    callback: Optional[ProgressCallback] = None,
    parallel: bool = False,
    workers: Optional[int] = None
) -> BatchCompressResult:
    """
    批量压缩（根据路径映射恢复压缩）
    
    Args:
        mappings: 路径映射列表 (archive_path -> extracted_path)
        delete_source: 压缩后删除源目录
        format: 压缩格式 (默认 zip)
        callback: 进度回调
        parallel: 是否并行
        workers: 并行工作线程数
    """
    reset_shutdown_event()
    
    bz_path = find_bz_executable()
    if not bz_path:
        return BatchCompressResult(
            success=False,
            message="未找到 Bandizip (bz.exe)，请安装或设置环境变量 BANDIZIP_PATH"
        )
    
    if not mappings:
        return BatchCompressResult(success=False, message="没有路径映射")
    
    # 过滤有效的映射（源目录必须存在）
    valid_mappings = [
        m for m in mappings 
        if Path(m.extracted_path).exists()
    ]
    
    if not valid_mappings:
        return BatchCompressResult(success=False, message="没有有效的源目录")
    
    total = len(valid_mappings)
    
    if callback:
        callback.log(f"开始压缩 {total} 个目录...")
        callback.progress(0, f"准备压缩 {total} 个目录")
    
    results: List[CompressResult] = []
    shutdown_event = get_shutdown_event()
    
    # Check if we can support unicode
    use_unicode = True
    try:
        if sys.platform == "win32":
            use_unicode = getattr(sys.stdout, "encoding", "").lower().replace("-", "") == "utf8"
    except Exception:
        use_unicode = False

    with Progress(
        SpinnerColumn(spinner_name="dots" if use_unicode else "simpleDots"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        main_task = progress.add_task(f"[cyan]压缩进度: 0/{total}", total=total)
        
        for idx, mapping in enumerate(valid_mappings):
            if shutdown_event.is_set():
                progress.console.print("[yellow]已取消剩余任务[/yellow]")
                break
            
            source = Path(mapping.extracted_path)
            archive = Path(mapping.archive_path)
            
            display_name = source.name[:40] + "..." if len(source.name) > 40 else source.name
            progress.update(main_task, description=f"[cyan]压缩: {display_name}")
            
            if callback:
                progress_pct = int(5 + (idx / total) * 90)
                callback.progress(progress_pct, f"压缩 {idx + 1}/{total}", source.name)
            
            result = compress_single(source, archive, bz_path, delete_source, format)
            results.append(result)
            
            if result.success:
                progress.console.print(
                    f"  [green]✓[/green] {display_name} → {archive.name} ({result.duration:.2f}s)"
                )
                if callback:
                    callback.log(f"✅ 压缩成功: {source.name} → {archive.name}")
            else:
                err_msg = result.error[:50] if result.error else "未知错误"
                progress.console.print(f"  [red]✗[/red] {display_name} | {err_msg}")
                if callback:
                    callback.log(f"❌ 压缩失败: {source.name} - {result.error}")
            
            progress.update(main_task, completed=idx + 1,
                           description=f"[cyan]压缩进度: {idx + 1}/{total}")
    
    compressed = sum(1 for r in results if r.success)
    failed = len(results) - compressed
    
    success = failed == 0
    message = f"压缩完成: {compressed} 成功, {failed} 失败"
    
    if callback:
        callback.progress(100, "压缩完成")
        callback.log(f"📊 {message}")
    
    return BatchCompressResult(
        success=success,
        message=message,
        compressed=compressed,
        failed=failed,
        total=total,
        results=results
    )


# ============ EFU 导出功能 ============

def export_efu(
    paths: List[Path],
    output_path: Path,
    open_in_everything: bool = True
) -> bool:
    """
    将路径列表导出为 Everything File List (EFU) 格式
    
    Args:
        paths: 要导出的路径列表（文件夹或文件）
        output_path: EFU 文件的输出路径
        open_in_everything: 是否自动用 Everything 打开
        
    Returns:
        是否成功导出
    """
    import os
    import csv
    
    try:
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入 EFU 文件 (UTF-8 with BOM for Windows compatibility)
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            # EFU 标题行
            writer.writerow(['Filename', 'Size', 'Date Modified', 'Date Created', 'Attributes'])
            
            for p in paths:
                if not p.exists():
                    continue
                    
                try:
                    stat = p.stat()
                    # Windows FILETIME: 100-nanosecond intervals since January 1, 1601
                    # Python timestamp: seconds since January 1, 1970
                    # 差值: 116444736000000000 (100-ns intervals)
                    EPOCH_DIFF = 116444736000000000
                    
                    mtime = int(stat.st_mtime * 10000000) + EPOCH_DIFF
                    ctime = int(stat.st_ctime * 10000000) + EPOCH_DIFF
                    
                    # 文件属性: 16 = 目录, 32 = 普通文件
                    attrs = 16 if p.is_dir() else 32
                    size = 0 if p.is_dir() else stat.st_size
                    
                    writer.writerow([str(p.resolve()), size, mtime, ctime, attrs])
                except Exception as e:
                    logger.warning(f"无法获取文件信息: {p} - {e}")
                    # 即使获取不到详细信息也写入基础信息
                    writer.writerow([str(p.resolve()), 0, 0, 0, 16 if p.is_dir() else 32])
        
        logger.info(f"已导出 {len(paths)} 个路径到 EFU: {output_path}")
        
        # 自动用 Everything 打开
        if open_in_everything:
            try:
                # 尝试查找 Everything 可执行文件
                everything_paths = [
                    Path(os.environ.get('PROGRAMFILES', '')) / 'Everything' / 'Everything.exe',
                    Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Everything' / 'Everything.exe',
                    Path(os.environ.get('LOCALAPPDATA', '')) / 'Everything' / 'Everything.exe',
                ]
                
                everything_exe = None
                for ep in everything_paths:
                    if ep.exists():
                        everything_exe = ep
                        break
                
                if everything_exe:
                    subprocess.Popen([str(everything_exe), '-filelist', str(output_path.resolve())])
                    logger.info(f"已用 Everything 打开: {output_path}")
                else:
                    # 尝试直接用关联程序打开
                    os.startfile(str(output_path.resolve()))
                    
            except Exception as e:
                logger.warning(f"无法自动打开 EFU: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"导出 EFU 失败: {e}")
        return False
