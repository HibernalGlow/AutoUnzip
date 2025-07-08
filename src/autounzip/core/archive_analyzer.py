#!/usr/bin/env python
"""
压缩包分析器 - 重构版本

使用模块化设计和7z命令统一处理各种压缩格式
"""

import os
import sys
import json
import datetime
from pathlib import Path
from typing import Dict, List, Union, Optional
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
import functools

# 导入Rich库
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from loguru import logger
# 导入模块化组件
from ..analyzers import (
    ArchiveInfo, FilterManager, BaseArchiveAnalyzer,
    get_file_type, is_archive_file, is_archive_type_supported,
    EXTRACT_MODE_ALL, EXTRACT_MODE_SELECTIVE, EXTRACT_MODE_SKIP
)

# 导入PageZ代码页检测模块
try:
    # 确保PageZ模块可以被导入
    from pagez.core.api import detect_archive_codepage
    PAGEZ_AVAILABLE = True
except Exception as e:
    logger.info(f"[yellow]警告: 无法导入PageZ模块: {str(e)}，将使用默认代码页[/yellow]")
    PAGEZ_AVAILABLE = False

# 设置Rich日志记录
console = Console()


def detect_codepage(archive_path: str) -> tuple:
    """检测压缩包的代码页
    
    Args:
        archive_path: 压缩包路径
        
    Returns:
        tuple: (代码页描述, 代码页参数)，如果无法检测则返回 ("", "")
    """
    # 如果PageZ不可用，返回空
    if not PAGEZ_AVAILABLE:
        return "", ""
        
    try:
        # 使用PageZ的代码页检测功能
        codepage_info = detect_archive_codepage(archive_path)
        codepage = str(codepage_info)
        codepage_param = codepage_info.param
        
        logger.info(f"[blue]为 {os.path.basename(archive_path)} 检测到代码页: {codepage_info}[/blue]")
        return codepage, codepage_param
    except Exception as e:
        logger.info(f"[yellow]代码页检测失败: {str(e)}，将使用默认代码页[/yellow]")
        return "", ""


def _analyze_single_archive(args: tuple) -> Optional[ArchiveInfo]:
    """独立的压缩包分析函数，用于多进程执行
    
    Args:
        args: 包含分析参数的元组 (file_path, extract_prefix, format_filters, archive_types)
        
    Returns:
        ArchiveInfo: 分析结果，如果失败返回None
    """
    file_path, extract_prefix, format_filters, archive_types = args
    
    try:
        # 创建临时的分析器组件
        filter_manager = FilterManager(format_filters)
        base_analyzer = BaseArchiveAnalyzer(filter_manager)
        
        # 转换为Path对象
        archive_path = Path(file_path)
        
        # 判断文件是否存在
        if not archive_path.exists() or not archive_path.is_file():
            return None
        
        # 获取文件信息
        name = archive_path.name
        size = archive_path.stat().st_size
        size_mb = size / (1024 * 1024)
        
        # 创建压缩包信息对象
        archive_info = ArchiveInfo(
            path=str(archive_path.absolute()),
            name=name,
            parent_path=str(archive_path.parent.absolute()),
            size=size,
            size_mb=size_mb
        )
        
        # 使用统一的分析器分析内容
        base_analyzer.analyze_archive_content(archive_info)
        
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
        _determine_extract_mode_helper(archive_info, filter_manager)
        
        # 推荐的解压路径
        extract_folder = (extract_prefix or "") + archive_path.stem  # 添加前缀 + 去掉扩展名的文件名
        default_extract_path = str((archive_path.parent / extract_folder).absolute())
        
        # 检查是否需要应用扁平化（这里无法获取全局设置，所以使用默认路径）
        archive_info.extract_path = default_extract_path
        
        # 检测代码页
        codepage, codepage_param = detect_codepage(str(archive_path.absolute()))
        archive_info.codepage = codepage
        archive_info.codepage_param = codepage_param
        
        return archive_info
        
    except Exception as e:
        # 创建错误记录
        error_info = {
            'path': str(Path(file_path).absolute()),
            'name': os.path.basename(file_path),
            'error_type': 'analysis_exception',
            'error_message': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        }
        return error_info


def _determine_extract_mode_helper(archive_info: ArchiveInfo, filter_manager: FilterManager) -> None:
    """辅助函数：根据压缩包内容确定解压模式和建议"""
    # 检查是否启用了部分解压模式
    part_mode = filter_manager.is_part_mode_enabled()
    
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
    
    # 如果启用了部分解压模式，设置为选择性解压
    if part_mode:
        archive_info.extract_mode = EXTRACT_MODE_SELECTIVE
        archive_info.recommendation = "部分解压模式：仅解压符合过滤条件的文件"
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


class ArchiveAnalyzer:
    """压缩包分析器，使用模块化设计和7z命令统一处理各种压缩格式"""
    def __init__(self, 
                 extract_prefix="[#a]", 
                 format_filters=None, 
                 archive_types=None,
                 use_multiprocessing=True,
                 max_workers=None):
        """初始化分析器
        
        Args:
            extract_prefix: 提取文件夹的前缀
            format_filters: 格式过滤配置，包含include/exclude/formats/type/part
            archive_types: 要处理的压缩包格式列表
            use_multiprocessing: 是否使用多进程分析，默认为True
            max_workers: 最大工作进程数，默认为CPU核心数
        """
        self.archive_infos = []
        self.output_json_path = None
        self.extract_prefix = extract_prefix
        self.error_archives = []
        self.archive_types = archive_types or []
        self.use_multiprocessing = use_multiprocessing
        self.max_workers = max_workers or cpu_count()
        self.flatten_single_folder = False  # 默认关闭扁平化
        
        # 初始化组件
        self.filter_manager = FilterManager(format_filters)
        self.base_analyzer = BaseArchiveAnalyzer(self.filter_manager)
    
    def analyze_archive(self, archive_path: Union[str, Path], parent_path: str = "") -> Optional[ArchiveInfo]:
        """分析单个压缩包"""
        try:
            # 转换为Path对象
            archive_path = Path(archive_path) if isinstance(archive_path, str) else archive_path
            
            # 判断文件是否存在
            if not archive_path.exists() or not archive_path.is_file():
                logger.info(f"[red]错误: 压缩包不存在或不是文件: {archive_path}[/red]")
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
            
            # 使用统一的分析器分析内容
            self.base_analyzer.analyze_archive_content(archive_info)
            
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
            extract_folder = (self.extract_prefix or "") + archive_path.stem  # 添加前缀 + 去掉扩展名的文件名
            default_extract_path = str((archive_path.parent / extract_folder).absolute())
            
            # 如果启用了扁平化且是单层文件夹结构，修改解压路径
            if self.flatten_single_folder and archive_info.is_single_folder:
                # 直接解压到压缩包所在目录
                archive_info.extract_path = str(archive_path.parent.absolute())
                console.print(f"[cyan]应用扁平化：将解压到 {archive_info.extract_path}[/cyan]")
            else:
                # 使用默认解压路径
                archive_info.extract_path = default_extract_path
            
            # 检测代码页
            codepage, codepage_param = detect_codepage(str(archive_path.absolute()))
            archive_info.codepage = codepage
            archive_info.codepage_param = codepage_param
            
            return archive_info
            
        except Exception as e:
            logger.info(f"[red]分析压缩包时出错: {str(e)}[/red]")
            import traceback
            logger.info(traceback.format_exc())
            self._record_error_archive(str(archive_path.absolute()), "analysis_exception", str(e))
            return None
    def _determine_extract_mode(self, archive_info: ArchiveInfo) -> None:
        """根据压缩包内容确定解压模式和建议"""
        # 检查是否启用了部分解压模式
        part_mode = self.filter_manager.is_part_mode_enabled()
        
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
        
        # 如果启用了部分解压模式，设置为选择性解压
        if part_mode:
            archive_info.extract_mode = EXTRACT_MODE_SELECTIVE
            archive_info.recommendation = "部分解压模式：仅解压符合过滤条件的文件"
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
    
    def _record_error_archive(self, archive_path: str, error_type: str, error_msg: str) -> None:
        """记录解压失败的压缩包
        
        Args:
            archive_path: 压缩包路径
            error_type: 错误类型
            error_msg: 错误消息
        """
        self.error_archives.append({
            'path': archive_path,
            'name': os.path.basename(archive_path),
            'error_type': error_type,
            'error_message': error_msg,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def save_error_json(self, output_path: str = None) -> str:
        """将解压错误记录保存为JSON文件
        
        Args:
            output_path: 输出文件路径，如果不指定则使用默认路径
            
        Returns:
            str: 输出文件路径
        """
        if not self.error_archives:
            return None
            
        # 如果未指定输出路径，创建默认路径
        if output_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"extraction_errors_{timestamp}.json"
            
        # 创建结果字典
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "error_count": len(self.error_archives),
            "errors": self.error_archives
        }
        
        # 保存到文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"[yellow]错误记录已保存到: {output_path}[/yellow]")
            self.output_json_path = output_path
            return output_path
        except Exception as e:
            logger.info(f"[red]保存错误记录时出错: {str(e)}[/red]")
            return None
    def scan_archives(self, target_path: Union[str, Path]) -> List[ArchiveInfo]:
        """扫描目录或文件，查找并分析所有压缩包"""
        target_path = Path(target_path) if isinstance(target_path, str) else target_path
        
        # 清空之前的分析结果
        self.archive_infos = []
        self.error_archives = []
        
        # 如果目标是文件而不是目录
        if target_path.is_file():
            if is_archive_file(str(target_path)):
                # 检查压缩包类型是否在支持列表中
                if self.archive_types and not is_archive_type_supported(str(target_path), self.archive_types):
                    logger.info(f"[yellow]跳过: 压缩包类型不在指定列表中: {target_path}[/yellow]")
                    return self.archive_infos
                
                archive_info = self.analyze_archive(target_path)
                if archive_info:
                    self.archive_infos.append(archive_info)
            else:
                logger.info(f"[yellow]警告: 不是支持的压缩包格式: {target_path}[/yellow]")
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
                        # 检查压缩包类型是否在支持列表中
                        if not self.archive_types or is_archive_type_supported(file_path, self.archive_types):
                            archive_files.append(file_path)
            
            # 显示过滤信息
            if self.archive_types:
                logger.info(f"[cyan]过滤压缩包类型: {', '.join(self.archive_types)}[/cyan]")
                
            # 更新进度
            progress.update(task, total=len(archive_files), completed=0)
            
            # 根据文件数量决定是否使用多进程
            if self.use_multiprocessing and len(archive_files) > 1:
                # 使用多进程分析
                logger.info(f"[cyan]使用多进程分析 ({self.max_workers} 个工作进程): {len(archive_files)} 个压缩包[/cyan]")
                self._analyze_archives_multiprocess(archive_files, progress, task)
            else:
                # 使用单进程分析
                if not self.use_multiprocessing:
                    logger.info(f"[cyan]使用单进程分析: {len(archive_files)} 个压缩包[/cyan]")
                self._analyze_archives_singleprocess(archive_files, progress, task)
                
        # 保存错误记录
        if self.error_archives:
            self.save_error_json()
            
        return self.archive_infos
    
    def _analyze_archives_singleprocess(self, archive_files: List[str], progress: Progress, task) -> None:
        """单进程分析压缩包"""
        for i, file_path in enumerate(archive_files):
            progress.update(task, description=f"[cyan]分析压缩包 ({i+1}/{len(archive_files)}): {os.path.basename(file_path)}")
            
            archive_info = self.analyze_archive(file_path)
            if archive_info:
                # 检查是否启用了部分解压模式
                part_mode = self.filter_manager.is_part_mode_enabled()
                
                if part_mode:
                    # 部分解压模式：总是处理压缩包，但在分析时会过滤文件
                    self.archive_infos.append(archive_info)
                else:
                    # 整体过滤模式：检查是否应该跳过整个压缩包
                    if self.filter_manager.should_skip_archive(archive_info):
                        logger.info(f"[yellow]跳过压缩包（不符合格式过滤条件）: {os.path.basename(file_path)}[/yellow]")
                    else:
                        self.archive_infos.append(archive_info)
                        
            progress.update(task, completed=i+1)
    
    def _analyze_archives_multiprocess(self, archive_files: List[str], progress: Progress, task) -> None:
        """多进程分析压缩包"""
        # 准备参数
        args_list = []
        for file_path in archive_files:
            args = (
                file_path,
                self.extract_prefix,
                self.filter_manager.format_filters,
                self.archive_types
            )
            args_list.append(args)
        
        # 使用进程池分析
        completed_count = 0
        
        try:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_file = {
                    executor.submit(_analyze_single_archive, args): args[0] 
                    for args in args_list
                }
                
                # 处理完成的任务
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    completed_count += 1
                    
                    progress.update(
                        task, 
                        description=f"[cyan]多进程分析 ({completed_count}/{len(archive_files)}): {os.path.basename(file_path)}",
                        completed=completed_count
                    )
                    
                    try:
                        result = future.result()
                        if result is not None:
                            # 检查结果是否是错误信息
                            if isinstance(result, dict) and 'error_type' in result:
                                # 这是一个错误记录
                                self.error_archives.append(result)
                            else:
                                # 这是一个正常的分析结果
                                archive_info = result
                                
                                # 检查是否启用了部分解压模式
                                part_mode = self.filter_manager.is_part_mode_enabled()
                                
                                if part_mode:
                                    # 部分解压模式：总是处理压缩包，但在分析时会过滤文件
                                    self.archive_infos.append(archive_info)
                                else:
                                    # 整体过滤模式：检查是否应该跳过整个压缩包
                                    if self.filter_manager.should_skip_archive(archive_info):
                                        logger.info(f"[yellow]跳过压缩包（不符合格式过滤条件）: {os.path.basename(file_path)}[/yellow]")
                                    else:
                                        self.archive_infos.append(archive_info)
                                        
                    except Exception as e:
                        # 记录处理异常
                        self._record_error_archive(file_path, "processing_exception", str(e))
                        
        except Exception as e:
            logger.info(f"[red]多进程分析时出错，回退到单进程模式: {str(e)}[/red]")
            # 如果多进程失败，回退到单进程
            self._analyze_archives_singleprocess(archive_files, progress, task)
    
    def save_to_json(self, output_path: Union[str, Path] = None) -> str:
        """将分析结果保存为JSON文件"""
        if not self.archive_infos:
            logger.info("[yellow]警告: 没有可保存的分析结果[/yellow]")
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
            "archives": []
        }
        
        # 为每个压缩包创建配置项
        for archive in self.archive_infos:
            archive_config = archive.to_dict()
            # 添加扁平化选项
            archive_config["flatten_single_folder"] = self.flatten_single_folder
            result["archives"].append(archive_config)
        
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


def display_archive_structure(archive_infos: List[ArchiveInfo], display_details: bool = True, extract_prefix: str = "[#a]") -> None:
    """在控制台显示压缩包结构的树状图"""
    if not archive_infos:
        logger.info("[yellow]没有可显示的压缩包信息[/yellow]")
        return
    
    # 创建根节点
    tree = Tree(f"[bold blue]压缩包分析结果[/bold blue] (前缀: {extract_prefix})")
    
    # 为每个压缩包创建节点
    for archive in archive_infos:
        # 创建压缩包节点，显示名称和大小
        size_str = f"{archive.size_mb:.2f} MB"
        archive_node = tree.add(f"[bold green]{archive.name}[/bold green] ({size_str})")
        
        # 添加基本信息
        archive_node.add(f"[cyan]路径:[/cyan] {archive.path}")
        archive_node.add(f"[cyan]解压路径:[/cyan] {archive.extract_path}")
        archive_node.add(f"[cyan]文件数量:[/cyan] {archive.file_count}")
        archive_node.add(f"[cyan]解压模式:[/cyan] {archive.extract_mode}")
        archive_node.add(f"[cyan]建议:[/cyan] {archive.recommendation}")
        
        # 显示代码页信息
        if archive.codepage:
            archive_node.add(f"[cyan]代码页:[/cyan] {archive.codepage}")
        
        # 显示单层文件夹信息
        if archive.is_single_folder:
            archive_node.add(f"[green]单层文件夹:[/green] {archive.single_folder_name}")
        else:
            archive_node.add(f"[yellow]多层结构[/yellow]")
        
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
    logger.info("\n")
    logger.info(Panel(tree, title="压缩包内容预览", border_style="blue"))
    logger.info("\n")


def analyze_archive(target_path: Union[str, Path], 
                 display: bool = True, 
                 output_json: bool = True, 
                 extract_prefix: str = "[#a]",
                 format_filters: dict = None,
                 archive_types: list = None,
                 use_multiprocessing: bool = True,
                 max_workers: int = None,
                 flatten_single_folder: bool = False) -> Optional[str]:
    """分析压缩包并返回JSON配置文件路径
    
    Args:
        target_path: 目标路径，可以是文件或目录
        display: 是否显示分析结果
        output_json: 是否输出JSON
        extract_prefix: 提取文件夹的前缀
        format_filters: 格式过滤配置，包含include/exclude/formats/type/part
        archive_types: 要处理的压缩包格式列表
        use_multiprocessing: 是否使用多进程分析
        max_workers: 最大工作进程数
        flatten_single_folder: 是否启用单层文件夹扁平化
    
    Returns:
        str: JSON配置文件路径，如果分析失败返回None
    """
    logger.info(f"[blue]正在分析压缩包: {target_path}[/blue]")
    
    # 创建分析器
    analyzer = ArchiveAnalyzer(
        extract_prefix=extract_prefix,
        format_filters=format_filters,
        archive_types=archive_types,
        use_multiprocessing=use_multiprocessing,
        max_workers=max_workers
    )
    
    # 设置扁平化选项
    analyzer.flatten_single_folder = flatten_single_folder
    
    # 扫描并分析压缩包
    archive_infos = analyzer.scan_archives(target_path)
    
    if not archive_infos:
        logger.info("[yellow]未找到任何压缩包或所有压缩包被过滤[/yellow]")
        return None
    
    # 显示分析结果
    if display:
        display_archive_structure(archive_infos, extract_prefix=extract_prefix)
      # 保存为JSON
    if output_json:
        # 使用目标路径作为输出目录
        target_path_obj = Path(target_path)
        if target_path_obj.is_file():
            # 如果是文件，使用文件所在目录
            output_dir = target_path_obj.parent
        else:
            # 如果是目录，直接使用该目录
            output_dir = target_path_obj
        
        # 生成输出文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"archive_analysis_{timestamp}.json"
        
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
    parser.add_argument('--no-multiprocessing', action='store_true', help='禁用多进程分析')
    parser.add_argument('--max-workers', type=int, default=None, help='最大工作进程数（默认为CPU核心数）')
    
    args = parser.parse_args()
    
    # 分析压缩包
    analyze_archive(
        args.path,
        display=not args.no_display,
        output_json=not args.no_json,
        use_multiprocessing=not args.no_multiprocessing,
        max_workers=args.max_workers
    )
