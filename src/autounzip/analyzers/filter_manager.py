"""
过滤管理器

负责处理文件格式过滤逻辑，包括包含/排除过滤器和压缩包级别过滤
"""

from typing import Dict, List, Set
from .file_type_detector import get_file_type
from .archive_info import ArchiveInfo


class FilterManager:
    """过滤管理器，处理文件和压缩包的过滤逻辑"""
    
    def __init__(self, format_filters: Dict = None):
        """初始化过滤管理器
        
        Args:
            format_filters: 格式过滤配置，包含include/exclude/formats/type/part等
        """
        self.format_filters = format_filters or {}
    
    def is_file_format_match(self, file_path: str, include_formats=None, exclude_formats=None, file_type=None) -> bool:
        """判断文件格式是否符合过滤条件
        
        Args:
            file_path: 文件路径
            include_formats: 包含的格式列表 (例如: ['jpg', 'png'])
            exclude_formats: 排除的格式列表 (例如: ['gif'])
            file_type: 文件类型 (例如: 'image', 'video')
            
        Returns:
            bool: 如果文件符合条件返回True，否则返回False
        """
        # 如果没有任何过滤条件，则通过所有文件
        if not include_formats and not exclude_formats and not file_type:
            return True
            
        # 获取文件扩展名（不带点）
        import os
        ext = os.path.splitext(file_path.lower())[1]
        if ext.startswith('.'):
            ext = ext[1:]
        
        # 获取文件类型
        current_file_type = get_file_type(file_path)
        
        # 检查文件类型
        if file_type and current_file_type != file_type:
            return False
        
        # 检查排除列表
        if exclude_formats and ext in exclude_formats:
            return False
        
        # 检查包含列表
        if include_formats and ext not in include_formats:
            return False
        
        return True
    
    def should_filter_file(self, file_path: str) -> bool:
        """判断文件是否应该被过滤掉
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 如果文件不符合过滤条件返回True，否则返回False
        """
        # 如果没有过滤条件，不过滤任何文件
        if not self.format_filters:
            return False
            
        # 提取过滤条件
        include_formats = self.format_filters.get('--include', [])
        exclude_formats = self.format_filters.get('--exclude', [])
        formats = self.format_filters.get('--formats', [])
        file_type = self.format_filters.get('--type')
        
        # 如果指定了formats，将其作为include_formats
        if formats and not include_formats:
            include_formats = formats
            
        # 检查文件是否符合条件
        return not self.is_file_format_match(file_path, include_formats, exclude_formats, file_type)
    
    def should_skip_archive(self, archive_info: ArchiveInfo) -> bool:
        """判断整个压缩包是否应该被跳过（基于格式过滤器）
        
        Args:
            archive_info: 压缩包信息对象
            
        Returns:
            bool: 如果压缩包应该被跳过返回True，否则返回False
        """
        # 如果没有过滤条件，不跳过任何压缩包
        if not self.format_filters:
            return False
            
        # 提取过滤条件
        include_formats = self.format_filters.get('--include', [])
        exclude_formats = self.format_filters.get('--exclude', [])
        formats = self.format_filters.get('--formats', [])
        file_type = self.format_filters.get('--type')
        
        # 如果指定了formats，将其作为include_formats
        if formats and not include_formats:
            include_formats = formats
        
        # 获取压缩包中的所有文件扩展名（去掉点号）
        archive_extensions = set()
        for ext in archive_info.file_extensions.keys():
            clean_ext = ext.lstrip('.')
            archive_extensions.add(clean_ext)
        
        # 获取压缩包中的所有文件类型
        archive_types = set(archive_info.file_types.keys())
        
        # 处理排除逻辑 (-e)
        if exclude_formats:
            for exclude_format in exclude_formats:
                exclude_format = exclude_format.lower()
                # 检查是否有匹配的扩展名
                if exclude_format in archive_extensions:
                    return True
        
        # 处理类型排除逻辑 (-t 配合 -e)
        if file_type and exclude_formats:
            if file_type.lower() in archive_types:
                return True
        
        # 处理包含逻辑 (-i)
        if include_formats:
            has_included_format = False
            for include_format in include_formats:
                include_format = include_format.lower()
                # 检查是否有匹配的扩展名
                if include_format in archive_extensions:
                    has_included_format = True
                    break
            
            # 如果没有找到任何包含的格式，跳过这个压缩包
            if not has_included_format:
                return True
        
        # 处理类型包含逻辑 (-t 配合 -i)
        if file_type and include_formats:
            if file_type.lower() not in archive_types:
                return True
        
        return False
    
    def is_part_mode_enabled(self) -> bool:
        """检查是否启用了部分解压模式
        
        Returns:
            bool: 如果启用了部分解压模式返回True，否则返回False
        """
        return self.format_filters.get('--part', False)
