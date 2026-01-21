"""
bandia - 批量解压/压缩工具
使用 Bandizip (bz.exe) 进行批量解压和压缩

功能：
- 解压: bandia extract [OPTIONS] [PATHS...]
- 压缩: bandia compress [OPTIONS] [PATHS...]
- 重压缩: bandia repack [OPTIONS] [MAPPING_FILE]

API 使用:
    from bandia import extract_batch, compress_batch
    from bandia.types import PathMapping
"""

# 导出核心函数供 API 使用
from .core import (
    extract_single,
    extract_batch,
    compress_single,
    compress_batch,
    get_output_path,
)

# 导出类型
from .types import (
    ExtractResult,
    BatchExtractResult,
    CompressResult,
    BatchCompressResult,
    PathMapping,
)

# 导出工具
from .utils import (
    ProgressCallback,
    find_bz_executable,
    parse_text_paths,
    filter_archives,
    get_shutdown_event,
    reset_shutdown_event,
)

__version__ = "2.0.0"
__all__ = [
    # 核心函数
    "extract_single",
    "extract_batch",
    "compress_single",
    "compress_batch",
    "get_output_path",
    # 类型
    "ExtractResult",
    "BatchExtractResult",
    "CompressResult",
    "BatchCompressResult",
    "PathMapping",
    # 工具
    "ProgressCallback",
    "find_bz_executable",
    "parse_text_paths",
    "filter_archives",
    "get_shutdown_event",
    "reset_shutdown_event",
]
