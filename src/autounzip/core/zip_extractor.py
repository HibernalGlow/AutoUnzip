"""
ZIP解压器 - 基于配置的压缩包解压工具

根据JSON配置文件进行解压操作，支持多种压缩格式和解压选项
"""

import os
import sys
import json
import zipfile
import shutil
import subprocess
import re
import time
from pathlib import Path
from typing import List, Dict, Union, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

# 导入Rich库
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel
from rich.logging import RichHandler
from rich.text import Text
from rich.progress import Progress, TextColumn, BarColumn, TaskID, SpinnerColumn
from rich.progress import TimeElapsedColumn, TimeRemainingColumn, FileSizeColumn, ProgressColumn

# 设置Rich日志记录器
console = Console()

# 导入ArchiveInfo类型
from autounzip.core.archive_analyzer import ArchiveInfo, EXTRACT_MODE_ALL, EXTRACT_MODE_SELECTIVE, EXTRACT_MODE_SKIP

# 导入PageZ代码页检测模块
try:
    # 确保PageZ模块可以被导入
    from pagez.core.api import detect_archive_codepage
    PAGEZ_AVAILABLE = True
except ImportError as e:
    console.print(f"[yellow]警告: 无法导入PageZ模块: {str(e)}，将使用默认代码页[/yellow]")
    PAGEZ_AVAILABLE = False

# 解压结果类型
@dataclass
class ExtractionResult:
    """解压操作的结果记录"""
    archive_path: str
    target_path: str
    success: bool
    extracted_files: int = 0
    elapsed_time: float = 0.0
    error_message: str = ""
    warnings: List[str] = None
    codepage: str = ""  # 添加代码页信息
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PercentageColumn(ProgressColumn):
    """自定义进度列，显示百分比"""
    def render(self, task):
        if task.total == 0:
            return Text("0%")
        return Text(f"{task.completed / task.total:.0%}")


class ExtractionTracker:
    """解压进度跟踪器"""
    
    def __init__(self, progress: Progress = None):
        """初始化跟踪器"""
        self.progress = progress
        self.task_id = None
        self.file_task_id = None
        self.total_task_id = None  # 总体进度任务ID
        self.total_archives = 0
        self.processed_archives = 0
        self.current_file = ""
        self.total_files = 0
        self.processed_files = 0
        self._last_update_time = 0
    
    def update_from_output(self, line: str) -> None:
        """从解压工具输出更新进度"""
        # 匹配"正在解压"、"Extracting"等输出中的文件名部分
        file_match = re.search(r"(解压|Extracting|Extract|Inflate)\s+(.+)", line, re.IGNORECASE)
        if file_match:
            self.current_file = file_match.group(2).strip()
            self.processed_files += 1
            if self.progress and self.file_task_id is not None:
                # 更新文件进度
                self.progress.update(
                    self.file_task_id, 
                    description=f"[green]当前文件: {self.current_file}[/]"
                )
            return
            
        # 匹配百分比进度
        percent_match = re.search(r"(\d+)%", line)
        if percent_match and self.progress and self.file_task_id is not None:
            percent = int(percent_match.group(1))
            # 更新文件进度
            self.progress.update(
                self.file_task_id, 
                completed=percent,
                total=100
            )
    
    def start_archive(self, archive_name: str) -> None:
        """开始处理新的压缩包"""
        self.processed_archives += 1
        if self.progress:
            # 更新总体进度
            if self.task_id is not None:
                self.progress.update(
                    self.task_id, 
                    completed=self.processed_archives,
                    description=f"[cyan]总进度: {self.processed_archives}/{self.total_archives} 压缩包[/]"
                )
            # 更新固定在底部的总体进度
            if self.total_task_id is not None:
                self.progress.update(
                    self.total_task_id, 
                    completed=self.processed_archives,
                    description=f"[bold cyan]总体解压进度: {self.processed_archives}/{self.total_archives} 压缩包[/]"
                )
            # 重置当前文件进度
            if self.file_task_id is not None:
                self.progress.update(
                    self.file_task_id,
                    completed=0,
                    total=100,
                    description=f"[green]准备解压: {archive_name}[/]"
                )


class ZipExtractor:
    """压缩包解压器，支持多种压缩格式"""
    def __init__(self):
        """初始化解压器"""
        self.progress = None
        self.tracker = None
        self.filter_config = {}  # 存储过滤配置
        self._setup_progress()
    
    def _setup_progress(self) -> None:
        """设置进度显示"""
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            PercentageColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            expand=True
        )
        self.tracker = ExtractionTracker(self.progress)
    
    def get_codepage_param(self, archive_path: str, skip_codepage: bool = False) -> Optional[str]:
        """获取压缩包的代码页参数
        
        Args:
            archive_path: 压缩包路径
            skip_codepage: 是否跳过代码页检测，直接使用UTF-8
            
        Returns:
            代码页参数字符串，如 "-mcp=936"，如果无法检测则返回None
        """
        # 如果跳过代码页检测，直接返回UTF-8参数
        if skip_codepage:
            console.print(f"[cyan]跳过代码页检测，使用UTF-8: {os.path.basename(archive_path)}[/cyan]")
            return "-mcp=utf8"
        
        # 如果PageZ不可用，返回None
        if not PAGEZ_AVAILABLE:
            return None
            
        try:
            # 直接使用PageZ的代码页检测功能
            codepage_info = detect_archive_codepage(archive_path)
            codepage_param = codepage_info.param
            
            console.print(f"[blue]为 {os.path.basename(archive_path)} 检测到代码页: {codepage_info}[/blue]")
            return codepage_param
        except Exception as e:
            console.print(f"[yellow]代码页检测失败: {str(e)}，将使用默认代码页[/yellow]")
            return None
    
    def extract_from_json(self, config_path: Union[str, Path], delete_after_success: bool = False) -> List[ExtractionResult]:
        """根据JSON配置文件进行解压"""
        # 确保config_path是Path对象
        config_path = Path(config_path) if isinstance(config_path, str) else config_path
        
        # 读取配置文件
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            console.print(f"[red]读取配置文件出错: {str(e)}[/red]")
            return []
        
        # 提取过滤条件（如果存在）
        self.filter_config = config.get("filter_config", {})
        
        # 获取代码页设置
        skip_codepage = config.get("skip_codepage", False)
        
        # 获取待解压的压缩包列表
        archives = config.get("archives", [])
        
        if not archives:
            console.print("[yellow]配置文件中没有待解压的压缩包[/yellow]")
            return []
        
        # 设置解压进度
        self.tracker.total_archives = len(archives)
        self.tracker.processed_archives = 0
        
        # 创建进度显示
        with self.progress:
            # 创建总进度任务
            self.tracker.task_id = self.progress.add_task(
                f"[cyan]总进度: 0/{len(archives)} 压缩包[/]",
                total=len(archives),
                completed=0
            )
            
            # 创建当前文件进度任务
            self.tracker.file_task_id = self.progress.add_task(
                "[green]准备解压...[/]",
                total=100,
                completed=0
            )
            
            # 创建固定在底部的总体进度显示
            self.tracker.total_task_id = self.progress.add_task(
                f"[bold cyan]总体解压进度: 0/{len(archives)} 压缩包[/]",
                total=len(archives),
                completed=0
            )
            
            # 处理每个压缩包
            results = []
            for archive_config in archives:
                archive_path = archive_config.get("path", "")
                if not archive_path or not os.path.exists(archive_path):
                    console.print(f"[yellow]跳过不存在的压缩包: {archive_path}[/yellow]")
                    continue
                
                # 更新进度
                self.tracker.start_archive(os.path.basename(archive_path))
                
                # 提取解压配置
                extract_mode = archive_config.get("extract_mode", EXTRACT_MODE_ALL)
                extract_path = archive_config.get("extract_path", "")
                password = archive_config.get("password", "")
                flatten_single_folder = archive_config.get("flatten_single_folder", False)
                
                # 如果未指定解压路径，使用默认路径（压缩包所在目录下同名文件夹）
                if not extract_path:
                    archive_dir = os.path.dirname(archive_path)
                    archive_name = os.path.splitext(os.path.basename(archive_path))[0]
                    
                    # 检查是否启用了单层文件夹扁平化，并且该压缩包是单层文件夹结构
                    if flatten_single_folder:
                        # 需要先分析压缩包结构来判断是否为单层文件夹
                        from autounzip.core.archive_analyzer import ArchiveAnalyzer
                        temp_analyzer = ArchiveAnalyzer()
                        temp_info = temp_analyzer.analyze_archive(archive_path)
                        
                        if temp_info and temp_info.is_single_folder:
                            # 单层文件夹结构，直接解压到压缩包所在目录
                            extract_path = archive_dir
                            console.print(f"[cyan]检测到单层文件夹结构，将直接解压到: {extract_path}[/cyan]")
                        else:
                            # 不是单层文件夹结构，使用标准路径
                            extract_path = os.path.join(archive_dir, archive_name)
                    else:
                        # 未启用扁平化，使用标准路径
                        extract_path = os.path.join(archive_dir, archive_name)
                
                # 检查解压模式
                if extract_mode == EXTRACT_MODE_SKIP:
                    console.print(f"[yellow]跳过解压: {os.path.basename(archive_path)}[/yellow]")
                    continue
                
                # 检测代码页（只检测一次）
                codepage_param = self.get_codepage_param(archive_path, skip_codepage)
                
                # 执行解压
                try:
                    start_time = time.time()
                    result = self._extract_archive(
                        archive_path=archive_path,
                        target_path=extract_path,
                        password=password,
                        extract_mode=extract_mode,
                        archive_config=archive_config,
                        codepage_param=codepage_param  # 传入代码页参数
                    )
                    elapsed_time = time.time() - start_time
                    
                    # 记录结果
                    extraction_result = ExtractionResult(
                        archive_path=archive_path,
                        target_path=extract_path,
                        success=result[0],
                        extracted_files=result[1],
                        elapsed_time=elapsed_time,
                        error_message="" if result[0] else result[2],
                        codepage=codepage_param or "默认"  # 记录使用的代码页
                    )
                    
                    results.append(extraction_result)
                    
                    # 成功解压后删除源文件
                    if delete_after_success and result[0]:
                        try:
                            os.remove(archive_path)
                            console.print(f"[green]已删除源文件: {os.path.basename(archive_path)}[/green]")
                        except Exception as e:
                            console.print(f"[yellow]删除源文件失败: {str(e)}[/yellow]")
                            extraction_result.warnings.append(f"删除源文件失败: {str(e)}")
                    
                except Exception as e:
                    console.print(f"[red]解压出错: {str(e)}[/red]")
                    results.append(ExtractionResult(
                        archive_path=archive_path,
                        target_path=extract_path,
                        success=False,
                        error_message=str(e)
                    ))
        
        return results
    
    def _extract_archive(self, archive_path: str, target_path: str, password: str = "", 
                        extract_mode: str = EXTRACT_MODE_ALL, archive_config: dict = None,
                        codepage_param: Optional[str] = None) -> Tuple[bool, int, str]:
        """解压单个压缩包，使用7z命令统一处理所有格式，返回(成功标志, 解压文件数, 错误信息)"""
        # 确保目标目录存在
        os.makedirs(target_path, exist_ok=True)
        
        # 统一使用7z命令解压
        try:
            return self._extract_with_7zip_selective(archive_path, target_path, password, extract_mode, archive_config, codepage_param)
        except Exception as e:
            return False, 0, str(e)
    
    def _extract_with_7zip_selective(self, archive_path: str, target_path: str, password: str = "", 
                                    extract_mode: str = EXTRACT_MODE_ALL, archive_config: dict = None,
                                    codepage_param: Optional[str] = None) -> Tuple[bool, int, str]:
        """使用7zip命令行工具解压文件，支持选择性解压"""
        try:
            # 检查是否需要扁平化解压
            flatten_single_folder = archive_config.get("flatten_single_folder", False) if archive_config else False
            is_single_folder = archive_config.get("is_single_folder", False) if archive_config else False
            
            # 如果启用扁平化且是单层文件夹，不指定输出目录
            if flatten_single_folder and is_single_folder:
                # 使用压缩包所在目录作为目标路径
                target_path = os.path.dirname(archive_path)
                original_cwd = os.getcwd()
                os.chdir(target_path)
                
                try:
                    # 构建命令，不使用 -o 参数
                    cmd = ["7z", "x", archive_path, "-y"]
                    console.print(f"[cyan]扁平化解压：在目录 {target_path} 中直接解压[/cyan]")
                finally:
                    # 确保恢复原始工作目录
                    os.chdir(original_cwd)
            else:
                # 正常解压，指定输出目录
                cmd = ["7z", "x", f"-o{target_path}", archive_path, "-y"]
            
            # 如果需要密码
            if password:
                cmd.append(f"-p{password}")
            
            # 添加代码页参数
            if codepage_param:
                cmd.append(codepage_param)
                console.print(f"[blue]使用代码页参数: {codepage_param}[/blue]")
            
            # 检查是否需要选择性解压
            if extract_mode == EXTRACT_MODE_SELECTIVE:
                wildcards = self._generate_7z_wildcards()
                if wildcards:
                    console.print(f"[blue]部分解压模式，过滤规则: {', '.join(wildcards)}[/blue]")
                    # 添加通配符到命令
                    cmd.extend(wildcards)
                else:
                    console.print("[yellow]选择性解压模式但无过滤条件，将解压所有文件[/yellow]")
            
            # 执行命令
            console.print(f"[cyan]执行命令: {' '.join(cmd)}[/cyan]")
            
            # 如果是扁平化解压，需要在目标目录中执行命令
            if flatten_single_folder and is_single_folder:
                original_cwd = os.getcwd()
                os.chdir(target_path)
                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        universal_newlines=True,
                        bufsize=1,
                        stdin=subprocess.DEVNULL
                    )
                finally:
                    # 确保恢复原始工作目录
                    os.chdir(original_cwd)
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    universal_newlines=True,
                    bufsize=1,
                    stdin=subprocess.DEVNULL
                )
            
            # 跟踪进度
            extracted_files = 0
            for line in process.stdout:
                line = line.strip()
                # console.print(f"[dim]{line}[/dim]")  # 隐藏7z输出
                
                # 更新进度
                self.tracker.update_from_output(line)
                
                # 统计解压的文件数
                if "Extracting" in line or "- " in line:
                    extracted_files += 1
            
            # 等待进程结束
            return_code = process.wait()
            
            if return_code == 0:
                console.print(f"[green]解压完成，共提取 {extracted_files} 个文件[/green]")
                return True, extracted_files, ""
            else:
                error_msg = f"7zip返回错误代码: {return_code}"
                console.print(f"[red]{error_msg}[/red]")
                return False, extracted_files, error_msg
        
        except Exception as e:
            error_msg = f"执行7zip命令出错: {str(e)}"
            console.print(f"[red]{error_msg}[/red]")
            return False, 0, error_msg
    
    def _should_extract_file(self, file_path: str) -> bool:
        """根据过滤条件判断是否应该解压指定文件"""
        if not self.filter_config:
            return True
            
        # 导入FilterManager进行文件过滤判断
        from ..analyzers.filter_manager import FilterManager
        filter_manager = FilterManager(self.filter_config)
        
        # 检查是否为部分解压模式
        if not filter_manager.is_part_mode_enabled():
            return True
            
        # 文件级别过滤：如果文件不符合条件则跳过
        return not filter_manager.should_filter_file(file_path)
    
    def _generate_7z_wildcards(self) -> List[str]:
        """根据过滤条件生成7z通配符模式"""
        if not self.filter_config:
            return []
            
        from ..analyzers.filter_manager import FilterManager
        filter_manager = FilterManager(self.filter_config)
        
        # 如果不是部分解压模式，返回空列表
        if not filter_manager.is_part_mode_enabled():
            return []
            
        wildcards = []
        include_formats = self.filter_config.get('--include', [])
        exclude_formats = self.filter_config.get('--exclude', [])
        
        # 生成包含模式的通配符
        if include_formats:
            for ext in include_formats:
                # 移除点号前缀（如果存在）
                clean_ext = ext.lstrip('.')
                wildcards.append(f"*.{clean_ext}")
        
        # 注意：7z的排除模式需要特殊处理，这里先实现包含模式
        return wildcards
    
