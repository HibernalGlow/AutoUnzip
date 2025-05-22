#!/usr/bin/env python
"""
压缩包分析器

分析压缩包结构，识别压缩文件类型和内容，并生成解压配置JSON
"""

import os
import sys
import json
import zipfile
import rarfile
import py7zr
import logging
import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from collections import Counter

# 导入Rich库
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.logging import RichHandler

# 设置Rich日志记录
console = Console()

# 压缩文件后缀列表
ARCHIVE_EXTENSIONS = {
    'zip': ['.zip', '.cbz'],
    'rar': ['.rar', '.cbr'],
    '7z': ['.7z', '.cb7'],
    'tar': ['.tar', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz'],
}

# 默认文件类型映射
DEFAULT_FILE_TYPES = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.ico'],
    'text': ['.txt', '.md', '.rtf', '.log', '.ini', '.conf', '.cfg'],
    'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt'],
    'video': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.m4v', '.webm'],
    'audio': ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma'],
    'code': ['.py', '.js', '.html', '.css', '.json', '.xml', '.c', '.cpp', '.java', '.php', '.pl'],
    'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.cbz', '.cbr', '.cb7'],
}

# 解压模式常量
EXTRACT_MODE_ALL = "all"          # 解压所有文件
EXTRACT_MODE_SELECTIVE = "selective"  # 选择性解压
EXTRACT_MODE_SKIP = "skip"        # 跳过解压

@dataclass
class ArchiveInfo:
    """单个压缩包的信息"""
    path: str
    name: str
    parent_path: str = ""  # 父目录路径
    size: int = 0
    size_mb: float = 0.0
    extract_mode: str = EXTRACT_MODE_ALL  # 默认解压所有内容
    recommendation: str = ""
    file_count: int = 0
    file_types: Dict[str, int] = field(default_factory=dict)  # 文件类型统计
    file_extensions: Dict[str, int] = field(default_factory=dict)  # 文件扩展名统计
    dominant_types: List[str] = field(default_factory=list)  # 主要文件类型
    extract_path: str = ""  # 推荐的解压路径
    password_required: bool = False  # 是否需要密码
    password: str = ""  # 解压密码
    nested_archives: List["ArchiveInfo"] = field(default_factory=list)  # 嵌套的压缩包
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于JSON序列化"""
        result = asdict(self)
        # 移除嵌套对象，避免递归问题
        result.pop("nested_archives", None)
        return result
    
    def to_tree_dict(self) -> Dict[str, Any]:
        """转换为树结构的字典表示"""
        result = self.to_dict()
        # 添加嵌套压缩包信息
        if self.nested_archives:
            result["nested_archives"] = [nested.to_tree_dict() for nested in self.nested_archives]
        return result


def get_file_type(file_path: str) -> str:
    """根据文件扩展名确定文件类型"""
    ext = os.path.splitext(file_path.lower())[1]
    
    for file_type, extensions in DEFAULT_FILE_TYPES.items():
        if ext in extensions:
            return file_type
    
    return "unknown"


def is_archive_file(file_path: str) -> bool:
    """判断文件是否为压缩文件"""
    ext = os.path.splitext(file_path.lower())[1]
    for exts in ARCHIVE_EXTENSIONS.values():
        if ext in exts:
            return True
    return False


class ArchiveAnalyzer:
    """压缩包分析器，识别压缩包内容并生成解压配置"""
    
    def __init__(self):
        """初始化分析器"""
        self.archive_infos = []
        self.output_json_path = None
    
    def analyze_archive(self, archive_path: Union[str, Path], parent_path: str = "") -> Optional[ArchiveInfo]:
        """分析单个压缩包"""
        try:
            # 转换为Path对象
            archive_path = Path(archive_path) if isinstance(archive_path, str) else archive_path
            
            # 判断文件是否存在
            if not archive_path.exists() or not archive_path.is_file():
                console.print(f"[red]错误: 压缩包不存在或不是文件: {archive_path}[/red]")
                return None
            
            # 获取文件信息
            name = archive_path.name
            size = archive_path.stat().st_size
            size_mb = size / (1024 * 1024)
            
            # 创建压缩包信息对象
            archive_info = ArchiveInfo(
                path=str(archive_path.absolute()),
                name=name,
                parent_path=parent_path or str(archive_path.parent.absolute()),
                size=size,
                size_mb=size_mb
            )
            
            # 根据文件扩展名确定压缩包类型并分析内容
            ext = archive_path.suffix.lower()
            
            if ext in ARCHIVE_EXTENSIONS['zip']:
                self._analyze_zip(archive_info)
            elif ext in ARCHIVE_EXTENSIONS['rar']:
                self._analyze_rar(archive_info)
            elif ext in ARCHIVE_EXTENSIONS['7z']:
                self._analyze_7z(archive_info)
            elif ext in ARCHIVE_EXTENSIONS['tar']:
                self._analyze_tar(archive_info)
            else:
                console.print(f"[yellow]警告: 不支持的压缩包格式: {ext}[/yellow]")
                archive_info.recommendation = f"不支持的格式: {ext}"
                archive_info.extract_mode = EXTRACT_MODE_SKIP
            
            # 确定主要文件类型
            if archive_info.file_types:
                # 排序文件类型，按数量从大到小
                sorted_types = sorted(
                    archive_info.file_types.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                # 取前三个主要类型
                archive_info.dominant_types = [t[0] for t in sorted_types[:3]]
            
            # 根据内容确定解压模式和建议
            self._determine_extract_mode(archive_info)
            
            # 推荐的解压路径
            extract_folder = archive_path.stem  # 去掉扩展名的文件名
            archive_info.extract_path = str((archive_path.parent / extract_folder).absolute())
            
            return archive_info
            
        except Exception as e:
            console.print(f"[red]分析压缩包时出错: {str(e)}[/red]")
            import traceback
            console.print(traceback.format_exc())
            return None
    
    def _analyze_zip(self, archive_info: ArchiveInfo) -> None:
        """分析ZIP压缩包内容"""
        try:
            with zipfile.ZipFile(archive_info.path, 'r') as zip_file:
                # 获取文件列表
                file_list = zip_file.namelist()
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
                
                # 检查是否需要密码
                try:
                    # 尝试读取第一个文件内容
                    if file_list:
                        zip_file.read(file_list[0])
                except RuntimeError as e:
                    if "password required" in str(e).lower():
                        archive_info.password_required = True
                        archive_info.recommendation = "需要密码才能解压"
        
        except zipfile.BadZipFile:
            console.print(f"[red]错误: 损坏的ZIP文件: {archive_info.path}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "ZIP文件已损坏"
        except Exception as e:
            console.print(f"[red]分析ZIP文件时出错: {str(e)}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = f"分析出错: {str(e)}"
    
    def _analyze_rar(self, archive_info: ArchiveInfo) -> None:
        """分析RAR压缩包内容"""
        try:
            with rarfile.RarFile(archive_info.path) as rar_file:
                # 获取文件列表
                file_list = rar_file.namelist()
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
                
                # 检查是否需要密码
                try:
                    # 尝试读取第一个文件内容
                    if file_list:
                        rar_file.read(file_list[0])
                except rarfile.PasswordRequired:
                    archive_info.password_required = True
                    archive_info.recommendation = "需要密码才能解压"
        
        except rarfile.BadRarFile:
            console.print(f"[red]错误: 损坏的RAR文件: {archive_info.path}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "RAR文件已损坏"
        except Exception as e:
            console.print(f"[red]分析RAR文件时出错: {str(e)}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = f"分析出错: {str(e)}"
    
    def _analyze_7z(self, archive_info: ArchiveInfo) -> None:
        """分析7Z压缩包内容"""
        try:
            with py7zr.SevenZipFile(archive_info.path, mode='r') as sz_file:
                # 获取文件列表
                file_list = sz_file.getnames()
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
                
                # 检查是否需要密码 (py7zr会在打开时检查密码)
                if sz_file.needs_password():
                    archive_info.password_required = True
                    archive_info.recommendation = "需要密码才能解压"
        
        except py7zr.Bad7zFile:
            console.print(f"[red]错误: 损坏的7Z文件: {archive_info.path}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "7Z文件已损坏"
        except Exception as e:
            console.print(f"[red]分析7Z文件时出错: {str(e)}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = f"分析出错: {str(e)}"
    
    def _analyze_tar(self, archive_info: ArchiveInfo) -> None:
        """分析TAR压缩包内容"""
        import tarfile
        try:
            with tarfile.open(archive_info.path) as tar_file:
                # 获取文件列表
                file_list = tar_file.getnames()
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
        
        except tarfile.ReadError:
            console.print(f"[red]错误: 损坏的TAR文件: {archive_info.path}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "TAR文件已损坏"
        except Exception as e:
            console.print(f"[red]分析TAR文件时出错: {str(e)}[/red]")
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = f"分析出错: {str(e)}"
    
    def _determine_extract_mode(self, archive_info: ArchiveInfo) -> None:
        """根据压缩包内容确定解压模式和建议"""
        # 默认解压所有文件
        archive_info.extract_mode = EXTRACT_MODE_ALL
        
        # 如果压缩包已损坏，跳过解压
        if archive_info.extract_mode == EXTRACT_MODE_SKIP:
            return
        
        # 如果需要密码且未提供密码，推荐跳过
        if archive_info.password_required and not archive_info.password:
            archive_info.extract_mode = EXTRACT_MODE_SKIP
            archive_info.recommendation = "需要密码才能解压"
            return
        
        # 如果压缩包内容主要是图片，推荐全部解压
        if 'image' in archive_info.dominant_types:
            archive_info.extract_mode = EXTRACT_MODE_ALL
            archive_info.recommendation = "图片压缩包，建议全部解压"
            return
        
        # 如果压缩包包含多种文件类型，推荐选择性解压
        if len(archive_info.dominant_types) > 2:
            archive_info.extract_mode = EXTRACT_MODE_SELECTIVE
            archive_info.recommendation = "混合内容，建议选择需要的文件解压"
            return
        
        # 根据文件数量判断
        if archive_info.file_count > 100:
            archive_info.extract_mode = EXTRACT_MODE_SELECTIVE
            archive_info.recommendation = f"文件数量较多({archive_info.file_count}个)，建议选择性解压"
            return
        
        # 默认建议
        archive_info.recommendation = "建议全部解压"
    
    def scan_archives(self, target_path: Union[str, Path]) -> List[ArchiveInfo]:
        """扫描目录或文件，查找并分析所有压缩包"""
        target_path = Path(target_path) if isinstance(target_path, str) else target_path
        
        # 清空之前的分析结果
        self.archive_infos = []
        
        # 如果目标是文件而不是目录
        if target_path.is_file():
            if is_archive_file(str(target_path)):
                archive_info = self.analyze_archive(target_path)
                if archive_info:
                    self.archive_infos.append(archive_info)
            else:
                console.print(f"[yellow]警告: 不是支持的压缩包格式: {target_path}[/yellow]")
            return self.archive_infos
        
        # 如果目标是目录，扫描所有压缩文件
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            expand=True
        ) as progress:
            # 显示进度
            task = progress.add_task(f"[cyan]扫描目录: {target_path}...", total=None)
            
            # 遍历目录查找压缩文件
            archive_files = []
            for root, _, files in os.walk(target_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if is_archive_file(file_path):
                        archive_files.append(file_path)
            
            # 更新进度
            progress.update(task, total=len(archive_files), completed=0)
            
            # 分析每个压缩文件
            for i, file_path in enumerate(archive_files):
                progress.update(task, description=f"[cyan]分析压缩包 ({i+1}/{len(archive_files)}): {os.path.basename(file_path)}")
                archive_info = self.analyze_archive(file_path)
                if archive_info:
                    self.archive_infos.append(archive_info)
                progress.update(task, completed=i+1)
        
        return self.archive_infos
    
    def save_to_json(self, output_path: Union[str, Path] = None) -> str:
        """将分析结果保存为JSON文件"""
        if not self.archive_infos:
            console.print("[yellow]警告: 没有可保存的分析结果[/yellow]")
            return None
        
        # 如果未指定输出路径，创建一个临时文件
        if output_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"archive_analysis_{timestamp}.json"
        
        # 确保输出路径是字符串
        output_path = str(output_path) if isinstance(output_path, Path) else output_path
        
        # 创建结果字典
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "archives": [archive.to_dict() for archive in self.archive_infos]
        }
        
        # 保存到文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            console.print(f"[green]分析结果已保存到: {output_path}[/green]")
            self.output_json_path = output_path
            return output_path
        except Exception as e:
            console.print(f"[red]保存分析结果时出错: {str(e)}[/red]")
            return None


def display_archive_structure(archive_infos: List[ArchiveInfo], display_details: bool = True) -> None:
    """在控制台显示压缩包结构的树状图"""
    if not archive_infos:
        console.print("[yellow]没有可显示的压缩包信息[/yellow]")
        return
    
    # 创建根节点
    tree = Tree("[bold blue]压缩包分析结果[/bold blue]")
    
    # 为每个压缩包创建节点
    for archive in archive_infos:
        # 创建压缩包节点，显示名称和大小
        size_str = f"{archive.size_mb:.2f} MB"
        archive_node = tree.add(f"[bold green]{archive.name}[/bold green] ({size_str})")
        
        # 添加基本信息
        archive_node.add(f"[cyan]路径:[/cyan] {archive.path}")
        archive_node.add(f"[cyan]文件数量:[/cyan] {archive.file_count}")
        archive_node.add(f"[cyan]解压模式:[/cyan] {archive.extract_mode}")
        archive_node.add(f"[cyan]建议:[/cyan] {archive.recommendation}")
        
        # 如果需要密码，显示警告
        if archive.password_required:
            archive_node.add("[yellow]需要密码才能解压[/yellow]")
        
        if display_details:
            # 添加文件类型信息
            if archive.file_types:
                types_node = archive_node.add("[cyan]文件类型分布:[/cyan]")
                for file_type, count in archive.file_types.items():
                    types_node.add(f"[blue]{file_type}:[/blue] {count}个文件")
            
            # 添加文件扩展名信息
            if archive.file_extensions:
                exts_node = archive_node.add("[cyan]文件扩展名分布:[/cyan]")
                for ext, count in archive.file_extensions.items():
                    exts_node.add(f"[blue]{ext}:[/blue] {count}个文件")
    
    # 在控制台显示树
    console.print("\n")
    console.print(Panel(tree, title="压缩包内容预览", border_style="blue"))
    console.print("\n")


def analyze_archive(target_path: Union[str, Path], display: bool = True, output_json: bool = True) -> Optional[str]:
    """分析压缩包并返回JSON配置文件路径"""
    console.print(f"[blue]正在分析压缩包: {target_path}[/blue]")
    
    # 创建分析器
    analyzer = ArchiveAnalyzer()
    
    # 扫描并分析压缩包
    archive_infos = analyzer.scan_archives(target_path)
    
    if not archive_infos:
        console.print("[yellow]未找到任何压缩包[/yellow]")
        return None
    
    # 显示分析结果
    if display:
        display_archive_structure(archive_infos)
    
    # 保存为JSON
    if output_json:
        # 创建输出目录
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"archive_analysis_{timestamp}.json")
        
        # 保存配置
        return analyzer.save_to_json(output_path)
    
    return None


if __name__ == "__main__":
    # 命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='分析压缩包内容并生成解压配置')
    parser.add_argument('path', help='要分析的压缩包或目录路径')
    parser.add_argument('--no-display', action='store_true', help='不显示分析结果')
    parser.add_argument('--no-json', action='store_true', help='不生成JSON配置文件')
    
    args = parser.parse_args()
    
    # 分析压缩包
    analyze_archive(
        args.path,
        display=not args.no_display,
        output_json=not args.no_json
    )
