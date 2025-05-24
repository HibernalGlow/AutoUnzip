"""
基础压缩包分析器

使用7z命令行工具统一分析各种格式的压缩包
"""

import os
import subprocess
import re
from pathlib import Path
from typing import List, Optional
from collections import Counter

from rich.console import Console
from .archive_info import ArchiveInfo, EXTRACT_MODE_SKIP
from .file_type_detector import get_file_type, is_archive_file
from .filter_manager import FilterManager

console = Console()


class BaseArchiveAnalyzer:
    """基础压缩包分析器，使用7z命令统一分析各种压缩格式"""
    
    def __init__(self, filter_manager: FilterManager = None):
        """初始化分析器
        
        Args:
            filter_manager: 过滤管理器实例
        """
        self.filter_manager = filter_manager or FilterManager()
        
    def check_7z_available(self) -> bool:
        """检查7z命令是否可用
        
        Returns:
            bool: 如果7z命令可用返回True，否则返回False
        """
        try:
            result = subprocess.run(['7z'], capture_output=True, text=True, timeout=5)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def list_archive_files(self, archive_path: str) -> List[str]:
        """使用7z命令列出压缩包中的文件
        
        Args:
            archive_path: 压缩包路径
            
        Returns:
            List[str]: 文件列表，如果失败返回空列表
        """
        try:
            # 使用7z -l命令列出文件
            cmd = ['7z', 'l', '-slt', archive_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                console.print(f"[red]7z命令执行失败: {result.stderr}[/red]")
                return []
            
            # 解析7z输出
            files = []
            lines = result.stdout.split('\n')
            current_file = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    if current_file.get('Path') and current_file.get('Attributes', '').startswith('D') == False:
                        # 只添加文件，不添加目录
                        files.append(current_file['Path'])
                    current_file = {}
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    current_file[key.strip()] = value.strip()
            
            # 处理最后一个文件
            if current_file.get('Path') and current_file.get('Attributes', '').startswith('D') == False:
                files.append(current_file['Path'])
            
            return files
            
        except subprocess.TimeoutExpired:
            console.print(f"[red]7z命令超时: {archive_path}[/red]")
            return []
        except Exception as e:
            console.print(f"[red]分析压缩包时出错: {str(e)}[/red]")
            return []
    
    def analyze_archive_content(self, archive_info: ArchiveInfo) -> None:
        """分析压缩包内容并更新ArchiveInfo
        
        Args:
            archive_info: 要更新的压缩包信息对象
        """
        # 检查7z是否可用
        if not self.check_7z_available():
            console.print("[red]错误: 未找到7z命令，请确保已安装7-Zip[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "缺少7z命令，无法分析"
            return
        
        # 获取文件列表
        all_files = self.list_archive_files(archive_info.path)
        
        if not all_files:
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "无法读取压缩包内容或压缩包为空"
            return
        
        # 检查是否启用部分解压模式
        part_mode = self.filter_manager.is_part_mode_enabled()
        
        if part_mode:
            # 部分解压模式：应用文件格式过滤
            file_list = [f for f in all_files if not self.filter_manager.should_filter_file(f)]
            
            # 显示过滤信息
            if len(file_list) != len(all_files):
                console.print(f"[cyan]已过滤 {len(all_files) - len(file_list)} 个文件[/cyan]")
        else:
            # 整体过滤模式：不进行文件级别过滤
            file_list = all_files
        
        archive_info.file_count = len(file_list)
        
        # 统计文件类型
        file_types_counter = Counter()
        extensions_counter = Counter()
        
        # 检查是否有嵌套的压缩包
        nested_archives = []
        
        for file_path in file_list:
            # 获取文件扩展名
            _, ext = os.path.splitext(file_path.lower())
            if ext:
                extensions_counter[ext] += 1
            
            # 确定文件类型
            file_type = get_file_type(file_path)
            file_types_counter[file_type] += 1
            
            # 检查是否是压缩文件
            if is_archive_file(file_path):
                nested_archives.append(file_path)
        
        # 更新压缩包信息
        archive_info.file_types = dict(file_types_counter)
        archive_info.file_extensions = dict(extensions_counter)
        
        # 检查文件数量
        if archive_info.file_count == 0:
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            if part_mode:
                archive_info.recommendation = "没有符合条件的文件需要解压"
            else:
                archive_info.recommendation = "压缩包为空"
            return
        
        # 检查是否需要密码（通过尝试获取更详细信息）
        self._check_password_required(archive_info)
    
    def _check_password_required(self, archive_info: ArchiveInfo) -> None:
        """检查压缩包是否需要密码
        
        Args:
            archive_info: 压缩包信息对象
        """
        try:
            # 尝试使用7z测试压缩包
            cmd = ['7z', 't', archive_info.path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # 检查输出中是否包含密码相关信息
            if result.returncode != 0:
                error_text = result.stderr.lower()
                if 'wrong password' in error_text or 'password' in error_text:
                    archive_info.password_required = True
                elif 'corrupted' in error_text or 'damaged' in error_text:
                    archive_info.extract_mode = EXTRACT_MODE_SKIP
                    archive_info.recommendation = "压缩包已损坏"
                    
        except subprocess.TimeoutExpired:
            console.print(f"[yellow]密码检查超时: {archive_info.name}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]无法检查密码状态: {str(e)}[/yellow]")
