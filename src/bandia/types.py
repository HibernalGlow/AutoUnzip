"""
bandia 数据类型定义
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class ExtractResult:
    """单个文件解压结果"""
    path: Path
    success: bool
    duration: float = 0.0
    file_size: int = 0
    error: str = ""
    output_path: Optional[Path] = None


@dataclass
class BatchExtractResult:
    """批量解压结果"""
    success: bool
    message: str
    extracted: int = 0
    failed: int = 0
    total: int = 0
    results: List[ExtractResult] = field(default_factory=list)


@dataclass
class CompressResult:
    """单个压缩结果"""
    source_path: Path
    archive_path: Path
    success: bool
    duration: float = 0.0
    error: str = ""


@dataclass
class BatchCompressResult:
    """批量压缩结果"""
    success: bool
    message: str
    compressed: int = 0
    failed: int = 0
    total: int = 0
    results: List[CompressResult] = field(default_factory=list)


@dataclass
class PathMapping:
    """路径映射 - 用于重新压缩"""
    archive_path: str  # 原压缩包路径
    extracted_path: str  # 解压后目录路径
