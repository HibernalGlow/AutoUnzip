import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List

import pyperclip
from send2trash import send2trash
from loguru import logger
from datetime import datetime
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

BZ_EXECUTABLE_NAMES = ["bz.exe", "bandizip", "Bandizip", "BZ.exe"]

def setup_logger(app_name="app", project_root=None, console_output=True):
    """配置 Loguru 日志系统
    
    Args:
        app_name: 应用名称，用于日志目录
        project_root: 项目根目录，默认为当前文件所在目录
        console_output: 是否输出到控制台，默认为True
        
    Returns:
        tuple: (logger, config_info)
            - logger: 配置好的 logger 实例
            - config_info: 包含日志配置信息的字典
    """
    # 获取项目根目录
    if project_root is None:
        project_root = Path(__file__).parent.resolve()
    
    # 清除默认处理器
    logger.remove()
    
    # 有条件地添加控制台处理器（简洁版格式）
    if console_output:
        logger.add(
            sys.stdout,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>{elapsed}</blue> | <level>{level.icon} {level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
    
    # 使用 datetime 构建日志路径
    current_time = datetime.now()
    date_str = current_time.strftime("%Y-%m-%d")
    hour_str = current_time.strftime("%H")
    minute_str = current_time.strftime("%M%S")
    
    # 构建日志目录和文件路径
    log_dir = os.path.join(project_root, "logs", app_name, date_str, hour_str)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{minute_str}.log")
    
    # 添加文件处理器
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {elapsed} | {level.icon} {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,     )
    
    # 创建配置信息字典
    config_info = {
        'log_file': log_file,
    }
    
    logger.info(f"日志系统已初始化，应用名称: {app_name}")
    return logger, config_info

# 初始化模块级 logger
logger, config_info = setup_logger(app_name="bandia", console_output=True)


def find_bz_executable(candidate_dirs: Iterable[Path] | None = None) -> Path | None:
    """尝试自动定位 bz.exe。

    1. 环境变量 BANDIZIP_PATH 指定的路径。
    2. 传入的 candidate_dirs。
    3. PATH 中可执行。
    4. 常见安装目录。
    """
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

    # PATH
    for name in BZ_EXECUTABLE_NAMES:
        path = shutil.which(name) if 'shutil' in globals() else None  # 延迟导入避免不必要覆盖
        if path:
            return Path(path)

    # 常见安装目录
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


QUOTE_CHARS = '"“”\'\'‘’'
ARCHIVE_EXT_RE = re.compile(r"\.(zip|7z|rar|tar|gz|bz2|xz)$", re.IGNORECASE)


def _strip_outer_quotes(s: str) -> str:
    s = s.strip()
    # 去除成对或不成对的前后引号
    while len(s) >= 2 and s[0] in QUOTE_CHARS and s[-1] in QUOTE_CHARS:
        s = s[1:-1].strip()
    if s and s[0] in QUOTE_CHARS:
        s = s[1:].strip()
    if s and s[-1] in QUOTE_CHARS:
        s = s[:-1].strip()
    return s


def parse_text_paths(text: str) -> List[Path]:
    """从文本解析潜在路径。更宽松：
    - 按行
    - 去除各种引号
    - 若整行非路径但含有含扩展名的片段，尝试提取最后一个带压缩扩展的片段
    """
    raw_lines = text.replace("\r", "\n").split("\n")
    lines = [l for l in (rl.strip() for rl in raw_lines) if l]
    results: List[Path] = []
    for line in lines:
        cleaned = _strip_outer_quotes(line)
        if not ARCHIVE_EXT_RE.search(cleaned):
            # 尝试在行中寻找带扩展的子串
            m = ARCHIVE_EXT_RE.search(line)
            if m:
                # 回溯到空白或引号边界
                end = m.end()
                start = line.rfind(' ', 0, end) + 1
                cand = line[start:end]
                cleaned = _strip_outer_quotes(cand)
        # 再次检查
        if not ARCHIVE_EXT_RE.search(cleaned):
            logger.debug(f"忽略非压缩路径行: {line}")
            continue
        p = Path(cleaned)
        results.append(p)
    # 去重，保持顺序
    seen = set()
    uniq: List[Path] = []
    for p in results:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    logger.debug("解析得到路径:" + ("\n" + "\n".join(str(p) for p in uniq) if uniq else " <空>"))
    return uniq


def run_once(paths: List[Path], bz_path: Path, sleep_after: float = 0.0, delete: bool = True, use_trash: bool = True):
    for p in paths:
        if not p.exists():
            logger.error(f"不存在: {p}")
            continue
        if p.is_dir():
            logger.warning(f"跳过目录: {p}")
            continue
        logger.info(f"解压: {p}")
        cmd = [str(bz_path), "x", "-target:auto", str(p)]
        start = time.time()
        try:
            logger.debug("执行命令: " + " ".join(cmd))
            # 隐藏原生命令行输出：捕获 stdout/stderr，失败时再显示
            # 指定 encoding 与 errors，避免在含有非本地编码字节时触发 UnicodeDecodeError
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:  # noqa
            logger.exception(f"执行失败 {p}: {e}")
            continue
        duration = time.time() - start
        ok = proc.returncode == 0
        if ok:
            logger.success(f"成功 ({duration:.2f}s): {p}")
            if delete:
                try:
                    if use_trash:
                        send2trash(str(p))
                        logger.info(f"已移入回收站: {p}")
                    else:
                        p.unlink()
                        logger.info(f"已删除: {p}")
                except Exception as e:  # noqa
                    logger.error(f"删除失败 {p}: {e}")
        else:
            logger.error(f"失败 rc={proc.returncode}: {p}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        if sleep_after > 0:
            time.sleep(sleep_after)


def filter_archives(paths: List[Path]) -> List[Path]:
    exts = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz'}
    return [p for p in paths if p.suffix.lower() in exts]


def run(paths: List[Path], delete: bool = True, use_trash: bool = True):
    """执行一次批量解压。"""
    bz = find_bz_executable()
    if not bz:
        logger.error("未找到 bz.exe，请设置环境变量 BANDIZIP_PATH 或加入 PATH")
        return 1
    logger.info(f"使用 Bandizip: {bz}")
    if not paths:
        logger.warning("没有待处理路径")
        return 0
    paths = filter_archives(paths)
    if not paths:
        logger.warning("未发现支持的压缩格式")
        return 0
    run_once(paths, bz, delete=delete, use_trash=use_trash)
    return 0


def main():  # CLI 入口（一次性执行）
    import argparse

    parser = argparse.ArgumentParser(prog="bandia", description="批量解压 (Bandizip) - 剪贴板 / 参数 / 交互")
    parser.add_argument("paths", nargs="*", help="直接提供的压缩包路径 (可多个)")
    parser.add_argument("--clipboard", action="store_true", help="仅使用剪贴板 (覆盖默认)")
    parser.add_argument("--no-clipboard", action="store_true", help="禁用默认的剪贴板尝试")
    parser.add_argument("--delete", action="store_true", help="成功后删除源压缩包 (物理删除，不进回收站)")
    parser.add_argument("--trash", action="store_true", help="成功后放入回收站 (默认行为，若同时给出 --delete 优先级更高)")
    parser.add_argument("--keep", action="store_true", help="保留源压缩包 (覆盖 --delete / --trash)")
    parser.add_argument("--yes", action="store_true", help="非交互模式：不再询问")
    parser.add_argument("--debug", action="store_true", help="显示调试日志")
    args = parser.parse_args()

    if args.debug:
        logger.enable(__name__)
    collected: List[Path] = []

    def add_clipboard():
        try:
            text = pyperclip.paste()
        except Exception as e:  # noqa
            logger.error(f"读取剪贴板失败: {e}")
            return
        cps = parse_text_paths(text)
        if cps:
            console.print(f"[bold green]剪贴板提取 {len(cps)} 个路径[/bold green]")
        collected.extend(cps)

    # 默认：若未显式提供路径且未禁用，则尝试剪贴板
    if not args.paths and not args.clipboard and not args.no_clipboard:
        add_clipboard()
        # 默认删除
        default_delete = True
    else:
        default_delete = False

    if args.clipboard:
        add_clipboard()

    if args.paths:
        collected.extend([Path(p) for p in args.paths])

    # 若仍无 => 交互获取
    if not collected:
        console.print("[yellow]未获取到任何路径，进入交互模式。[/yellow]")
        # 兼容不同版本 rich：不使用 prompt_suffix，直接把提示写入问题文本
        choice = Prompt.ask(
            "来源 (1=手动多行 2=剪贴板)",
            choices=["1", "2"],
            default="1",
            show_choices=False,
            show_default=True,
        )
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

    # 规范化 & 去重
    norm: List[Path] = []
    seen = set()
    for p in collected:
        p = p.expanduser()
        if p not in seen:
            seen.add(p)
            norm.append(p)
    collected = norm

    # 显示列表
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

    # 删除策略判定
    # 删除策略：keep > delete > trash(default maybe) > confirm
    if args.keep:
        delete = False
        use_trash = False
    elif args.delete:
        delete = True
        use_trash = False
    elif args.trash or default_delete:
        # 默认移入回收站
        if args.yes:
            delete = True
            use_trash = True
        else:
            delete = Confirm.ask("解压成功后移入回收站?", default=True)
            use_trash = delete
    else:
        if args.yes:
            delete = False
            use_trash = False
        else:
            delete = Confirm.ask("解压成功后删除源压缩包?", default=False)
            use_trash = False

    code = run(collected, delete=delete, use_trash=use_trash)
    sys.exit(code)


if __name__ == "__main__":
    main()
