"""
文件类型检测器

负责根据文件扩展名识别文件类型，判断是否为压缩文件等
"""

import os
from typing import Dict, Set

# 压缩文件后缀列表
ARCHIVE_EXTENSIONS = {
    'zip': ['.zip', '.cbz'],
    'rar': ['.rar', '.cbr'],
    '7z': ['.7z', '.cb7'],
    'tar': ['.tar', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz'],
}

# 默认文件类型映射
DEFAULT_FILE_TYPES = {
    "text": {".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".json", ".xml", ".yml", ".yaml", ".csv", ".convert"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico", ".raw", ".jxl", ".avif", ".psd"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".nov"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma", ".m4a", ".opus"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cbz", ".cbr"},
    "code": {".py", ".js", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".php", ".go", ".rs", ".rb", ".ts"},
    "font": {".ttf", ".otf", ".woff", ".woff2", ".eot"},
    "executable": {".exe", ".dll", ".bat", ".sh", ".msi", ".app", ".apk"},
    "model": {".pth", ".h5", ".pb", ".onnx", ".tflite", ".mlmodel", ".pt", ".bin", ".caffemodel"}
}


class FileTypeDetector:
    """文件类型检测器"""
    
    def __init__(self, file_types: Dict[str, Set[str]] = None):
        """初始化文件类型检测器
        
        Args:
            file_types: 自定义文件类型映射，如果不提供则使用默认映射
        """
        self.file_types = file_types or DEFAULT_FILE_TYPES
        
    def get_file_type(self, file_path: str) -> str:
        """根据文件扩展名确定文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 文件类型，如果未知则返回"unknown"
        """
        ext = os.path.splitext(file_path.lower())[1]
        
        for file_type, extensions in self.file_types.items():
            if ext in extensions:
                return file_type
        
        return "unknown"
    
    def is_archive_file(self, file_path: str) -> bool:
        """判断文件是否为压缩文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 如果是压缩文件返回True，否则返回False
        """
        ext = os.path.splitext(file_path.lower())[1]
        for exts in ARCHIVE_EXTENSIONS.values():
            if ext in exts:
                return True
        return False
    
    def is_archive_type_supported(self, file_path: str, archive_types: list) -> bool:
        """判断压缩包类型是否在指定的支持列表中
        
        Args:
            file_path: 文件路径
            archive_types: 支持的压缩包类型列表，如 ['zip', 'rar', '7z']
            
        Returns:
            bool: 如果压缩包类型在支持列表中返回True，否则返回False
        """
        if not archive_types:  # 如果未指定类型，默认支持所有类型
            return True
            
        ext = os.path.splitext(file_path.lower())[1]
        
        for archive_type, exts in ARCHIVE_EXTENSIONS.items():
            if ext in exts and archive_type in archive_types:
                return True
                
        return False


# 创建默认实例，提供便捷的函数接口
_default_detector = FileTypeDetector()

def get_file_type(file_path: str) -> str:
    """根据文件扩展名确定文件类型（便捷函数）"""
    return _default_detector.get_file_type(file_path)

def is_archive_file(file_path: str) -> bool:
    """判断文件是否为压缩文件（便捷函数）"""
    return _default_detector.is_archive_file(file_path)

def is_archive_type_supported(file_path: str, archive_types: list) -> bool:
    """判断压缩包类型是否在指定的支持列表中（便捷函数）"""
    return _default_detector.is_archive_type_supported(file_path, archive_types)
