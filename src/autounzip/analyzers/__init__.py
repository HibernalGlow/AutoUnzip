"""
压缩包分析器模块

包含各种用于分析压缩包的工具和类
"""

from .file_type_detector import FileTypeDetector, get_file_type, is_archive_file, is_archive_type_supported
from .filter_manager import FilterManager
from .base_analyzer import BaseArchiveAnalyzer
from .archive_info import ArchiveInfo, EXTRACT_MODE_ALL, EXTRACT_MODE_SELECTIVE, EXTRACT_MODE_SKIP

__all__ = [
    'FileTypeDetector',
    'get_file_type', 
    'is_archive_file',
    'is_archive_type_supported',
    'FilterManager',
    'BaseArchiveAnalyzer',
    'ArchiveInfo',
    'EXTRACT_MODE_ALL',
    'EXTRACT_MODE_SELECTIVE', 
    'EXTRACT_MODE_SKIP'
]
