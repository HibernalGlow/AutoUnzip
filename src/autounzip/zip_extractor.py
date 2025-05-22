"""
ZIP解压器 - 基于配置的压缩包解压工具

根据JSON配置文件进行解压操作，支持多种压缩格式和解压选项
"""

import os
import sys
import json
import zipfile
import rarfile
import py7zr
import shutil
import subprocess
import logging
import re
import time
import tarfile
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
from rich.live import Live

# 设置Rich日志记录器
console = Console()

# 导入ArchiveInfo类型
from autounzip.archive_analyzer import ArchiveInfo, EXTRACT_MODE_ALL, EXTRACT_MODE_SELECTIVE, EXTRACT_MODE_SKIP

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
                
                # 如果未指定解压路径，使用默认路径（压缩包所在目录下同名文件夹）
                if not extract_path:
                    archive_dir = os.path.dirname(archive_path)
                    archive_name = os.path.splitext(os.path.basename(archive_path))[0]
                    extract_path = os.path.join(archive_dir, archive_name)
                
                # 检查解压模式
                if extract_mode == EXTRACT_MODE_SKIP:
                    console.print(f"[yellow]跳过解压: {os.path.basename(archive_path)}[/yellow]")
                    continue
                
                # 执行解压
                try:
                    start_time = time.time()
                    result = self._extract_archive(
                        archive_path=archive_path,
                        target_path=extract_path,
                        password=password
                    )
                    elapsed_time = time.time() - start_time
                    
                    # 记录结果
                    extraction_result = ExtractionResult(
                        archive_path=archive_path,
                        target_path=extract_path,
                        success=result[0],
                        extracted_files=result[1],
                        elapsed_time=elapsed_time,
                        error_message="" if result[0] else result[2]
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
    
    def _extract_archive(self, archive_path: str, target_path: str, password: str = "") -> Tuple[bool, int, str]:
        """解压单个压缩包，返回(成功标志, 解压文件数, 错误信息)"""
        # 确保目标目录存在
        os.makedirs(target_path, exist_ok=True)
        
        # 根据文件扩展名选择解压方法
        ext = os.path.splitext(archive_path.lower())[1]
        
        try:
            if ext == '.zip' or ext == '.cbz':
                return self._extract_zip(archive_path, target_path, password)
            elif ext == '.rar' or ext == '.cbr':
                return self._extract_rar(archive_path, target_path, password)
            elif ext == '.7z' or ext == '.cb7':
                return self._extract_7z(archive_path, target_path, password)
            elif ext in ['.tar', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz']:
                return self._extract_tar(archive_path, target_path)
            else:
                return False, 0, f"不支持的压缩格式: {ext}"
        except Exception as e:
            return False, 0, str(e)
    
    def _extract_zip(self, zip_path: str, target_path: str, password: str = "") -> Tuple[bool, int, str]:
        """解压ZIP文件"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # 获取文件列表
                file_list = zip_file.namelist()
                
                # 如果需要密码
                if password:
                    pwd = password.encode('utf-8')  # zipfile需要bytes类型的密码
                else:
                    pwd = None
                
                # 解压所有文件
                for i, file_name in enumerate(file_list):
                    # 更新进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]解压: {file_name}[/]",
                        completed=int((i+1) / len(file_list) * 100)
                    )
                    
                    try:
                        zip_file.extract(file_name, target_path, pwd=pwd)
                    except zipfile.BadZipFile as e:
                        console.print(f"[yellow]解压文件出错: {file_name} - {str(e)}[/yellow]")
                
                return True, len(file_list), ""
        
        except zipfile.BadZipFile as e:
            console.print(f"[red]损坏的ZIP文件: {str(e)}[/red]")
            return False, 0, f"损坏的ZIP文件: {str(e)}"
        except Exception as e:
            console.print(f"[red]解压ZIP文件出错: {str(e)}[/red]")
            return False, 0, str(e)
    
    def _extract_rar(self, rar_path: str, target_path: str, password: str = "") -> Tuple[bool, int, str]:
        """解压RAR文件"""
        try:
            with rarfile.RarFile(rar_path) as rar_file:
                # 获取文件列表
                file_list = rar_file.namelist()
                
                # 如果需要密码
                if password:
                    rar_file.setpassword(password)
                
                # 解压所有文件
                for i, file_name in enumerate(file_list):
                    # 更新进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]解压: {file_name}[/]",
                        completed=int((i+1) / len(file_list) * 100)
                    )
                    
                    try:
                        rar_file.extract(file_name, target_path)
                    except Exception as e:
                        console.print(f"[yellow]解压文件出错: {file_name} - {str(e)}[/yellow]")
                
                return True, len(file_list), ""
        
        except rarfile.BadRarFile as e:
            console.print(f"[red]损坏的RAR文件: {str(e)}[/red]")
            return False, 0, f"损坏的RAR文件: {str(e)}"
        except rarfile.PasswordRequired:
            console.print(f"[red]RAR文件需要密码[/red]")
            return False, 0, "RAR文件需要密码"
        except Exception as e:
            console.print(f"[red]解压RAR文件出错: {str(e)}[/red]")
            return False, 0, str(e)
    
    def _extract_7z(self, sz_path: str, target_path: str, password: str = "") -> Tuple[bool, int, str]:
        """解压7Z文件"""
        try:
            # 如果需要密码
            if password:
                with py7zr.SevenZipFile(sz_path, mode='r', password=password) as sz_file:
                    # 获取文件列表
                    file_list = sz_file.getnames()
                    
                    # 更新进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]解压7Z文件...[/]",
                        completed=0
                    )
                    
                    # 解压所有文件
                    sz_file.extractall(target_path)
                    
                    # 完成进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]7Z解压完成[/]",
                        completed=100
                    )
                    
                    return True, len(file_list), ""
            else:
                with py7zr.SevenZipFile(sz_path, mode='r') as sz_file:
                    # 获取文件列表
                    file_list = sz_file.getnames()
                    
                    # 更新进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]解压7Z文件...[/]",
                        completed=0
                    )
                    
                    # 解压所有文件
                    sz_file.extractall(target_path)
                    
                    # 完成进度
                    self.progress.update(
                        self.tracker.file_task_id,
                        description=f"[green]7Z解压完成[/]",
                        completed=100
                    )
                    
                    return True, len(file_list), ""
        
        except py7zr.Bad7zFile as e:
            console.print(f"[red]损坏的7Z文件: {str(e)}[/red]")
            return False, 0, f"损坏的7Z文件: {str(e)}"
        except py7zr.PasswordRequired:
            console.print(f"[red]7Z文件需要密码[/red]")
            return False, 0, "7Z文件需要密码"
        except Exception as e:
            console.print(f"[red]解压7Z文件出错: {str(e)}[/red]")
            return False, 0, str(e)
    
    def _extract_tar(self, tar_path: str, target_path: str) -> Tuple[bool, int, str]:
        """解压TAR文件"""
        try:
            with tarfile.open(tar_path) as tar_file:
                # 获取文件列表
                file_list = tar_file.getnames()
                
                # 更新进度
                self.progress.update(
                    self.tracker.file_task_id,
                    description=f"[green]解压TAR文件...[/]",
                    completed=0
                )
                
                # 解压所有文件
                tar_file.extractall(target_path)
                
                # 完成进度
                self.progress.update(
                    self.tracker.file_task_id,
                    description=f"[green]TAR解压完成[/]",
                    completed=100
                )
                
                return True, len(file_list), ""
        
        except tarfile.ReadError as e:
            console.print(f"[red]损坏的TAR文件: {str(e)}[/red]")
            return False, 0, f"损坏的TAR文件: {str(e)}"
        except Exception as e:
            console.print(f"[red]解压TAR文件出错: {str(e)}[/red]")
            return False, 0, str(e)
    
    def _extract_with_7zip(self, archive_path: str, target_path: str, password: str = "") -> Tuple[bool, int, str]:
        """使用7zip命令行工具解压文件（备选方法）"""
        try:
            # 构建命令
            cmd = ["7z", "x", f"-o{target_path}", archive_path, "-y"]
            
            # 如果需要密码
            if password:
                cmd.append(f"-p{password}")
            
            # 执行命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )
            
            # 跟踪进度
            extracted_files = 0
            for line in process.stdout:
                line = line.strip()
                
                # 更新进度
                self.tracker.update_from_output(line)
                
                # 统计解压的文件数
                if "Extracting" in line:
                    extracted_files += 1
            
            # 等待进程结束
            return_code = process.wait()
            
            if return_code == 0:
                return True, extracted_files, ""
            else:
                return False, extracted_files, f"7zip返回错误代码: {return_code}"
        
        except Exception as e:
            console.print(f"[red]执行7zip命令出错: {str(e)}[/red]")
            return False, 0, str(e)


if __name__ == "__main__":
    # 简单的命令行测试
    import argparse
    parser = argparse.ArgumentParser(description='从JSON配置解压文件')
    parser.add_argument('config', help='JSON配置文件路径')
    parser.add_argument('-d', '--delete', action='store_true', help='解压成功后删除源文件')
    
    args = parser.parse_args()
    
    # 创建解压器并执行解压
    extractor = ZipExtractor()
    results = extractor.extract_from_json(args.config, delete_after_success=args.delete)
    
    # 输出结果
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    
    console.print(f"\n[green]成功解压: {success_count} 个压缩包[/green]")
    if fail_count > 0:
        console.print(f"[red]解压失败: {fail_count} 个压缩包[/red]")
        for result in results:
            if not result.success:
                console.print(f"[red]  - {os.path.basename(result.archive_path)}: {result.error_message}[/red]")
