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
    CompressResult, BatchCompressResult, PathMapping
)
from .utils import (
    find_bz_executable, filter_archives, get_shutdown_event, 
    reset_shutdown_event, ProgressCallback, DEFAULT_PARALLEL_WORKERS
)

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
    overwrite_mode: str = "overwrite"
) -> ExtractResult:
    """解压单个压缩包"""
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
    
    output_path = get_output_path(archive, bz_path)
    
    mode_flags = {"overwrite": "-aoa", "skip": "-aos", "rename": "-aou"}
    conflict_flag = mode_flags.get(overwrite_mode, "-aoa")
    
    cmd = [str(bz_path), "x", "-y", conflict_flag, "-target:auto", str(archive)]
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
    workers: Optional[int] = None
) -> BatchExtractResult:
    """批量解压压缩包"""
    reset_shutdown_event()
    
    bz_path = find_bz_executable()
    if not bz_path:
        return BatchExtractResult(
            success=False,
            message="未找到 Bandizip (bz.exe)，请安装或设置环境变量 BANDIZIP_PATH"
        )
    
    if callback:
        callback.log(f"使用 Bandizip: {bz_path}")
    
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
            workers or DEFAULT_PARALLEL_WORKERS, callback
        )
    else:
        results = _extract_sequential(
            paths, bz_path, delete, use_trash, overwrite_mode, callback
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
    callback: Optional[ProgressCallback]
) -> List[ExtractResult]:
    """串行解压"""
    results: List[ExtractResult] = []
    total = len(paths)
    shutdown_event = get_shutdown_event()
    
    with Progress(
        SpinnerColumn(),
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
            
            result = extract_single(archive, bz_path, delete, use_trash, overwrite_mode)
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
    callback: Optional[ProgressCallback]
) -> List[ExtractResult]:
    """并行解压"""
    results: List[ExtractResult] = []
    total = len(paths)
    completed = 0
    shutdown_event = get_shutdown_event()
    
    console.print(f"[cyan]⚡ 并行解压模式: {workers} 个工作线程[/cyan]")
    
    with Progress(
        SpinnerColumn(),
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
                    extract_single, archive, bz_path, delete, use_trash, overwrite_mode
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
    
    # 构建压缩命令
    # bz c [-y] [-sdel] <archive> <source>
    cmd = [str(bz_path), "c", "-y"]
    if delete_source:
        cmd.append("-sdel")  # 压缩后删除源文件
    cmd.extend([str(archive_path), str(source)])
    
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
        return CompressResult(source, archive_path, False, error=str(e))
    
    duration = time.time() - start_time
    
    if proc.returncode != 0:
        error_msg = proc.stderr or proc.stdout or f"返回码 {proc.returncode}"
        return CompressResult(source, archive_path, False, duration, error_msg[:200])
    
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
    
    with Progress(
        SpinnerColumn(),
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
