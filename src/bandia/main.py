"""
bandia - 批量解压工具
使用 Bandizip (bz.exe) 进行批量解压

功能：
- 支持剪贴板/参数/交互式输入
- 支持解压后删除源文件（可选移入回收站）
- 支持进度回调（用于 GUI/WebSocket 集成）
- 支持 .zip .7z .rar .tar .gz .bz2 .xz 格式
- 支持并行解压提升性能
- 支持 Ctrl+C 优雅中断
"""

import os
import re
import shutil
import subprocess
import sys
import time
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

import pyperclip
from send2trash import send2trash
from loguru import logger
from datetime import datetime
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.progress import (
    Progress, TextColumn, BarColumn, SpinnerColumn,
    TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn
)
from rich.panel import Panel

console = Console()

# 并行解压配置
DEFAULT_PARALLEL_WORKERS = max(2, min(4, (os.cpu_count() or 4) // 2))

# 全局中断标志
_shutdown_event = threading.Event()

BZ_EXECUTABLE_NAMES = ["bz.exe", "bandizip", "Bandizip", "BZ.exe"]
ARCHIVE_EXTENSIONS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz'}
QUOTE_CHARS = '"\u201c\u201d\'\u2018\u2019'
ARCHIVE_EXT_RE = re.compile(r"\.(zip|7z|rar|tar|gz|bz2|xz)$", re.IGNORECASE)


# ============ 数据类 ============

@dataclass
class ExtractResult:
    """单个文件解压结果"""
    path: Path
    success: bool
    duration: float = 0.0
    file_size: int = 0  # 压缩包大小 (bytes)
    error: str = ""



@dataclass
class BatchResult:
    """批量解压结果"""
    success: bool
    message: str
    extracted: int = 0
    failed: int = 0
    total: int = 0
    results: List[ExtractResult] = field(default_factory=list)


# ============ 进度回调类 ============

class ProgressCallback:
    """
    进度回调封装
    支持节流以减少回调频率，适用于 WebSocket 等场景
    """
    
    def __init__(
        self,
        on_progress: Optional[Callable[[int, str, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        throttle_interval: float = 0.0  # 0 表示不节流
    ):
        """
        Args:
            on_progress: 进度回调 (progress: 0-100, message: str, current_file: str)
            on_log: 日志回调 (message: str)
            throttle_interval: 节流间隔（秒），0 表示不节流
        """
        self.on_progress = on_progress
        self.on_log = on_log
        self.throttle_interval = throttle_interval
        self._last_progress_time = 0.0
        self._last_progress_value = -1
    
    def progress(self, value: int, message: str, current_file: str = ""):
        """发送进度（带可选节流）"""
        if not self.on_progress:
            return
        
        now = time.time()
        should_send = (
            self.throttle_interval <= 0 or
            value == 0 or 
            value == 100 or
            value - self._last_progress_value >= 5 or
            now - self._last_progress_time >= self.throttle_interval
        )
        
        if should_send:
            self.on_progress(value, message, current_file)
            self._last_progress_time = now
            self._last_progress_value = value
    
    def log(self, message: str):
        """发送日志"""
        if self.on_log:
            self.on_log(message)


# ============ 日志配置 ============

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统"""
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    logger.remove()
    
    if console_output:
        # 兼容 Windows GBK 控制台，如果无法设置编码则移除图标
        sink = sys.stdout
        fmt = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding='utf-8')
                fmt = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        except Exception:
            pass
            
        logger.add(sink, level="INFO", format=fmt)
    
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{minute_str}.log")
    
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,
    )
    
    config_info = {'log_file': log_file}
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info


# 初始化模块级 logger
logger, config_info = setup_logger(app_name="bandia", console_output=True)


# ============ 工具函数 ============

def find_bz_executable(candidate_dirs: Iterable[Path] | None = None) -> Path | None:
    """尝试自动定位 bz.exe"""
    env = os.getenv("BANDIZIP_PATH")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        for name in BZ_EXECUTABLE_NAMES:
            cand = p / name
            if cand.is_file():
                return cand

    if candidate_dirs:
        for d in candidate_dirs:
            for name in BZ_EXECUTABLE_NAMES:
                cand = d / name
                if cand.is_file():
                    return cand

    for name in BZ_EXECUTABLE_NAMES:
        path = shutil.which(name)
        if path:
            return Path(path)

    common_dirs = [
        Path("C:/Program Files/Bandizip"),
        Path("C:/Program Files (x86)/Bandizip"),
        Path.home() / "AppData/Local/Programs/Bandizip",
    ]
    for d in common_dirs:
        for name in BZ_EXECUTABLE_NAMES:
            cand = d / name
            if cand.is_file():
                return cand
    return None


def _strip_outer_quotes(s: str) -> str:
    """去除字符串两端的引号"""
    s = s.strip()
    while len(s) >= 2 and s[0] in QUOTE_CHARS and s[-1] in QUOTE_CHARS:
        s = s[1:-1].strip()
    if s and s[0] in QUOTE_CHARS:
        s = s[1:].strip()
    if s and s[-1] in QUOTE_CHARS:
        s = s[:-1].strip()
    return s


def parse_text_paths(text: str) -> List[Path]:
    """从文本解析压缩包路径"""
    raw_lines = text.replace("\r", "\n").split("\n")
    lines = [l for l in (rl.strip() for rl in raw_lines) if l]
    results: List[Path] = []
    
    for line in lines:
        cleaned = _strip_outer_quotes(line)
        if not ARCHIVE_EXT_RE.search(cleaned):
            m = ARCHIVE_EXT_RE.search(line)
            if m:
                end = m.end()
                start = line.rfind(' ', 0, end) + 1
                cand = line[start:end]
                cleaned = _strip_outer_quotes(cand)
        
        if not ARCHIVE_EXT_RE.search(cleaned):
            logger.debug(f"忽略非压缩路径行: {line}")
            continue
        results.append(Path(cleaned))
    
    # 去重保序
    seen = set()
    return [p for p in results if not (p in seen or seen.add(p))]


def filter_archives(paths: List[Path]) -> List[Path]:
    """过滤出有效的压缩包路径"""
    return [p for p in paths if p.suffix.lower() in ARCHIVE_EXTENSIONS]


# ============ 核心解压函数 ============

def extract_single(
    archive: Path,
    bz_path: Path,
    delete: bool = True,
    use_trash: bool = True,
    overwrite_mode: str = "overwrite"
) -> ExtractResult:
    """
    解压单个压缩包
    
    Args:
        archive: 压缩包路径
        bz_path: Bandizip 可执行文件路径
        delete: 解压成功后是否删除源文件
        use_trash: 是否使用回收站
        overwrite_mode: 冲突处理模式 ("overwrite", "skip", "rename")
    
    Returns:
        ExtractResult: 解压结果
    """
    # 检查中断
    if _shutdown_event.is_set():
        return ExtractResult(archive, False, error="用户中断")
    
    if not archive.exists():
        return ExtractResult(archive, False, error="文件不存在")
    
    if archive.is_dir():
        return ExtractResult(archive, False, error="是目录")
    
    # 获取文件大小
    try:
        file_size = archive.stat().st_size
    except Exception:
        file_size = 0
    
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
    
    # 解压成功，处理删除
    if delete:
        try:
            if use_trash:
                send2trash(str(archive))
            else:
                archive.unlink()
        except Exception as e:
            logger.warning(f"删除失败 {archive.name}: {e}")
    
    return ExtractResult(archive, True, duration, file_size)



def extract_batch(
    paths: List[Path],
    delete: bool = True,
    use_trash: bool = True,
    overwrite_mode: str = "overwrite",
    callback: Optional[ProgressCallback] = None,
    parallel: bool = False,
    workers: int = None
) -> BatchResult:
    """
    批量解压压缩包（支持可视化进度条和并行处理）
    
    Args:
        paths: 压缩包路径列表
        delete: 解压成功后是否删除源文件
        use_trash: 是否使用回收站
        overwrite_mode: 冲突处理模式
        callback: 进度回调（可选，用于 WebSocket 等场景）
        parallel: 是否启用并行解压
        workers: 并行工作线程数（默认自动计算）
    
    Returns:
        BatchResult: 批量解压结果
    """
    # 重置中断标志
    _shutdown_event.clear()
    
    # 查找 Bandizip
    bz_path = find_bz_executable()
    if not bz_path:
        return BatchResult(
            success=False,
            message="未找到 Bandizip (bz.exe)，请安装或设置环境变量 BANDIZIP_PATH"
        )
    
    if callback:
        callback.log(f"使用 Bandizip: {bz_path}")
    
    # 过滤有效路径
    paths = filter_archives(paths)
    if not paths:
        return BatchResult(success=False, message="没有有效的压缩包路径")
    
    total = len(paths)
    
    # 计算总文件大小（用于显示）
    total_size = 0
    for p in paths:
        try:
            total_size += p.stat().st_size
        except Exception:
            pass
    
    if callback:
        callback.log(f"开始解压 {total} 个压缩包...")
        callback.progress(0, f"准备解压 {total} 个文件")
    
    # 根据并行设置选择执行方式
    if parallel and total > 1:
        results = _extract_parallel(
            paths, bz_path, delete, use_trash, overwrite_mode,
            workers or DEFAULT_PARALLEL_WORKERS, callback
        )
    else:
        results = _extract_sequential(
            paths, bz_path, delete, use_trash, overwrite_mode, callback
        )
    
    # 统计结果
    extracted = sum(1 for r in results if r.success)
    failed = len(results) - extracted
    total_extracted_size = sum(r.file_size for r in results if r.success)
    
    success = failed == 0
    message = f"解压完成: {extracted} 成功, {failed} 失败"
    
    if callback:
        callback.progress(100, "解压完成")
        callback.log(f"📊 {message}")
    
    # 显示最终摘要
    console.print(f"\n[green]✓ 完成[/green] {extracted}/{len(results)} | "
                 f"总计 {total_extracted_size/1024/1024:.1f}MB")
    
    return BatchResult(
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
    """串行解压（带 Rich Progress 可视化）"""
    results: List[ExtractResult] = []
    total = len(paths)
    
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
            # 检查中断
            if _shutdown_event.is_set():
                progress.console.print("[yellow]已取消剩余任务[/yellow]")
                break
            
            display_name = archive.name[:40] + "..." if len(archive.name) > 40 else archive.name
            progress.update(main_task, description=f"[cyan]解压: {display_name}")
            
            # 计算进度回调百分比
            if callback:
                progress_pct = int(5 + (idx / total) * 90)
                callback.progress(progress_pct, f"STARTED:{idx}", archive.name)
                callback.progress(progress_pct, f"解压 {idx + 1}/{total}", archive.name)
            
            # 执行解压
            result = extract_single(archive, bz_path, delete, use_trash, overwrite_mode)
            results.append(result)
            
            # 显示单个任务结果
            if result.success:
                size_mb = result.file_size / 1024 / 1024
                progress.console.print(
                    f"  [green]✓[/green] {display_name} | "
                    f"{size_mb:.1f}MB ({result.duration:.2f}s)"
                )
                if callback:
                    callback.log(f"✅ 成功 ({result.duration:.2f}s): {archive.name}")
                logger.success(f"成功 ({result.duration:.2f}s): {archive}")
            else:
                err_msg = result.error[:50] if result.error else "未知错误"
                progress.console.print(f"  [red]✗[/red] {display_name} | {err_msg}")
                if callback:
                    callback.log(f"❌ 失败: {archive.name} - {result.error}")
                logger.error(f"失败: {archive} - {result.error}")
            
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
    """并行解压（支持 Ctrl+C 中断）"""
    results: List[ExtractResult] = []
    total = len(paths)
    completed = 0
    
    # 重置中断标志
    _shutdown_event.clear()
    
    # 仅在主线程中设置信号处理（避免在后台线程中出错）
    original_handler = None
    is_main_thread = threading.current_thread() is threading.main_thread()
    
    if is_main_thread:
        original_handler = signal.getsignal(signal.SIGINT)
        
        def signal_handler(signum, frame):
            console.print("\n[yellow]⚠️ 收到中断信号，正在停止...[/yellow]")
            _shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
    
    console.print(f"[cyan]⚡ 并行解压模式: {workers} 个工作线程[/cyan]")
    
    try:
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
                # 提交所有任务
                futures = {}
                for idx, archive in enumerate(paths):
                    if callback:
                        progress_pct = int(5 + (completed / total) * 90)
                        callback.progress(progress_pct, f"STARTED:{idx}", archive.name)
                    
                    future = executor.submit(
                        extract_single, archive, bz_path, delete, use_trash, overwrite_mode
                    )
                    futures[future] = (idx, archive)
                
                # 收集结果
                for future in as_completed(futures):
                    # 检查中断
                    if _shutdown_event.is_set():
                        for f in futures:
                            f.cancel()
                        progress.console.print("[yellow]已取消剩余任务[/yellow]")
                        break
                    
                    idx, archive = futures[future]
                    try:
                        result = future.result(timeout=0.1)
                        results.append(result)
                        completed += 1
                        
                        # 计算进度回调百分比
                        if callback:
                            progress_pct = int(5 + (completed / total) * 90)
                            # 发送 FINISHED:idx 消息，并保留原有的进度消息
                            callback.progress(progress_pct, f"FINISHED:{idx}|解压 {completed}/{total}", archive.name)
                        
                        # 显示单个任务结果
                        display_name = archive.name[:40] + "..." if len(archive.name) > 40 else archive.name
                        if result.success:
                            size_mb = result.file_size / 1024 / 1024
                            progress.console.print(
                                f"  [green]✓[/green] {display_name} | "
                                f"{size_mb:.1f}MB ({result.duration:.2f}s)"
                            )
                            if callback:
                                callback.log(f"✅ 成功 ({result.duration:.2f}s): {archive.name}")
                            logger.success(f"成功 ({result.duration:.2f}s): {archive}")
                        else:
                            err_msg = result.error[:50] if result.error else "未知错误"
                            progress.console.print(f"  [red]✗[/red] {display_name} | {err_msg}")
                            if callback:
                                callback.log(f"❌ 失败: {archive.name} - {result.error}")
                            logger.error(f"失败: {archive} - {result.error}")
                        
                        progress.update(main_task, completed=completed,
                                       description=f"[cyan]并行解压: {completed}/{total}")
                    except TimeoutError:
                        continue
                    except Exception as e:
                        completed += 1
                        results.append(ExtractResult(archive, False, error=str(e)))
                        progress.update(main_task, completed=completed)
    finally:
        # 恢复原始信号处理
        if is_main_thread and original_handler is not None:
            signal.signal(signal.SIGINT, original_handler)
    
    return results



# ============ 兼容旧 API ============

def run_once(paths: List[Path], bz_path: Path, sleep_after: float = 0.0, 
             delete: bool = True, use_trash: bool = True, overwrite_mode: str = "overwrite"):
    """执行解压操作（兼容旧 API）"""
    for p in paths:
        result = extract_single(p, bz_path, delete, use_trash, overwrite_mode)
        if result.success:
            logger.success(f"成功 ({result.duration:.2f}s): {p}")
            if delete:
                action = "已移入回收站" if use_trash else "已删除"
                logger.info(f"{action}: {p}")
        else:
            logger.error(f"失败: {p} - {result.error}")
        
        if sleep_after > 0:
            time.sleep(sleep_after)


def run(paths: List[Path], delete: bool = True, use_trash: bool = True, 
        overwrite_mode: str = "overwrite", parallel: bool = False, workers: int = None) -> int:
    """执行批量解压（兼容旧 API，支持并行）"""
    result = extract_batch(
        paths, delete, use_trash, overwrite_mode,
        parallel=parallel, workers=workers
    )
    if not result.success and result.total == 0:
        logger.error(result.message)
        return 1
    return 0 if result.success else 1


# ============ CLI 入口 ============

def main():
    import argparse

    parser = argparse.ArgumentParser(prog="bandia", description="批量解压 (Bandizip) - 剪贴板 / 参数 / 交互")
    parser.add_argument("paths", nargs="*", help="直接提供的压缩包路径 (可多个)")
    parser.add_argument("--clipboard", action="store_true", help="仅使用剪贴板 (覆盖默认)")
    parser.add_argument("--no-clipboard", action="store_true", help="禁用默认的剪贴板尝试")
    parser.add_argument("--delete", action="store_true", help="成功后删除源压缩包 (物理删除)")
    parser.add_argument("--trash", action="store_true", help="成功后放入回收站 (默认)")
    parser.add_argument("--keep", action="store_true", help="保留源压缩包")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在文件 (默认)")
    parser.add_argument("--skip", action="store_true", help="跳过已存在文件")
    parser.add_argument("--rename", action="store_true", help="自动重命名已存在文件")
    parser.add_argument("--yes", action="store_true", help="非交互模式")
    parser.add_argument("--parallel", "-P", action="store_true", help="启用并行解压")
    parser.add_argument("--workers", "-w", type=int, default=None, help="并行工作线程数")
    parser.add_argument("--debug", action="store_true", help="显示调试日志")
    args = parser.parse_args()

    if args.debug:
        logger.enable(__name__)
    
    collected: List[Path] = []

    def add_clipboard():
        try:
            text = pyperclip.paste()
        except Exception as e:
            logger.error(f"读取剪贴板失败: {e}")
            return
        cps = parse_text_paths(text)
        if cps:
            console.print(f"[bold green]剪贴板提取 {len(cps)} 个路径[/bold green]")
        collected.extend(cps)

    # 默认行为
    if not args.paths and not args.clipboard and not args.no_clipboard:
        add_clipboard()
        default_delete = True
    else:
        default_delete = False

    if args.clipboard:
        add_clipboard()

    if args.paths:
        collected.extend([Path(p) for p in args.paths])

    # 交互模式
    if not collected:
        console.print("[yellow]未获取到任何路径，进入交互模式。[/yellow]")
        choice = Prompt.ask("来源 (1=手动多行 2=剪贴板)", choices=["1", "2"], default="1", show_choices=False, show_default=True)
        if choice == "2":
            add_clipboard()
        else:
            console.print("输入多行路径，空行结束：")
            buf_lines: List[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if not line.strip():
                    break
                buf_lines.append(line)
            collected.extend(parse_text_paths("\n".join(buf_lines)))

    # 规范化去重
    seen = set()
    collected = [p.expanduser() for p in collected if not (p.expanduser() in seen or seen.add(p.expanduser()))]

    if collected:
        table = Table(title="待处理压缩包", show_lines=False)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("路径", style="magenta")
        for idx, p in enumerate(collected, 1):
            table.add_row(str(idx), str(p))
        console.print(table)
    else:
        console.print("[red]没有任何可处理路径，退出。[/red]")
        sys.exit(0)

    # 删除策略
    if args.keep:
        delete, use_trash = False, False
    elif args.delete:
        delete, use_trash = True, False
    elif args.trash or default_delete:
        if args.yes:
            delete, use_trash = True, True
        else:
            delete = Confirm.ask("解压成功后移入回收站?", default=True)
            use_trash = delete
    else:
        if args.yes:
            delete, use_trash = False, False
        else:
            delete = Confirm.ask("解压成功后删除源压缩包?", default=False)
            use_trash = False

    # 冲突处理模式
    if args.skip:
        overwrite_mode = "skip"
    elif args.rename:
        overwrite_mode = "rename"
    else:
        overwrite_mode = "overwrite"

    code = run(
        collected, delete=delete, use_trash=use_trash, 
        overwrite_mode=overwrite_mode, 
        parallel=args.parallel, workers=args.workers
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
