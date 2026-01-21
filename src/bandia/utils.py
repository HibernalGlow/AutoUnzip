"""
bandia 工具函数
"""

import os
import re
import shutil
import time
import threading
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from loguru import logger

# 全局中断标志
_shutdown_event = threading.Event()

BZ_EXECUTABLE_NAMES = ["bz.exe", "bandizip", "Bandizip", "BZ.exe"]
ARCHIVE_EXTENSIONS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz'}
QUOTE_CHARS = '""\u201c\u201d\'\u2018\u2019'
ARCHIVE_EXT_RE = re.compile(r"\.(zip|7z|rar|tar|gz|bz2|xz)$", re.IGNORECASE)

# 并行配置
DEFAULT_PARALLEL_WORKERS = max(2, min(4, (os.cpu_count() or 4) // 2))


def get_shutdown_event() -> threading.Event:
    """获取全局中断事件"""
    return _shutdown_event


def reset_shutdown_event():
    """重置中断标志"""
    _shutdown_event.clear()


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


def strip_outer_quotes(s: str) -> str:
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
        cleaned = strip_outer_quotes(line)
        if not ARCHIVE_EXT_RE.search(cleaned):
            m = ARCHIVE_EXT_RE.search(line)
            if m:
                end = m.end()
                start = line.rfind(' ', 0, end) + 1
                cand = line[start:end]
                cleaned = strip_outer_quotes(cand)
        
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


class ProgressCallback:
    """
    进度回调封装
    支持节流以减少回调频率，适用于 WebSocket 等场景
    """
    
    def __init__(
        self,
        on_progress: Optional[Callable[[int, str, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        throttle_interval: float = 0.0
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
