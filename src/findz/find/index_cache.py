"""
压缩包索引缓存模块
用于加速大规模压缩包搜索，避免重复扫描
"""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class FileEntry:
    """文件条目信息"""
    name: str  # 文件名
    path: str  # 完整路径
    size: int  # 文件大小
    mtime: float  # 修改时间戳
    is_archive: bool  # 是否为压缩包
    ext: str  # 扩展名
    archive_path: Optional[str] = None  # 如果在压缩包内，记录压缩包路径


@dataclass
class ArchiveIndex:
    """压缩包索引信息"""
    archive_path: str  # 压缩包路径
    archive_mtime: float  # 压缩包修改时间
    archive_size: int  # 压缩包大小
    file_count: int  # 内部文件数量
    files: List[FileEntry]  # 内部文件列表
    scan_time: float  # 扫描时间戳
    checksum: str  # 压缩包校验和（基于路径+大小+时间）


class IndexCache:
    """索引缓存管理器"""
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化索引缓存
        
        参数:
            cache_dir: 缓存目录路径，默认为用户主目录下的 .findz_cache
        """
        if cache_dir is None:
            cache_dir = os.path.join(Path.home(), ".findz_cache")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "archive_index.json"
        
        # 内存缓存
        self._cache: Dict[str, ArchiveIndex] = {}
        self._load_cache()
    
    def _load_cache(self):
        """从磁盘加载缓存"""
        if not self.cache_file.exists():
            return
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            for archive_path, index_data in data.items():
                # 反序列化文件条目
                files = [FileEntry(**f) for f in index_data['files']]
                index_data['files'] = files
                self._cache[archive_path] = ArchiveIndex(**index_data)
                
        except Exception as e:
            print(f"警告: 加载缓存失败: {e}")
            self._cache = {}
    
    def _save_cache(self):
        """保存缓存到磁盘"""
        try:
            data = {}
            for archive_path, index in self._cache.items():
                index_dict = asdict(index)
                data[archive_path] = index_dict
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"警告: 保存缓存失败: {e}")
    
    def _calculate_checksum(self, archive_path: str, size: int, mtime: float) -> str:
        """计算压缩包校验和"""
        data = f"{archive_path}:{size}:{mtime}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def get_index(self, archive_path: str) -> Optional[ArchiveIndex]:
        """
        获取压缩包索引
        
        参数:
            archive_path: 压缩包路径
            
        返回:
            索引信息，如果不存在或已过期返回 None
        """
        if archive_path not in self._cache:
            return None
        
        index = self._cache[archive_path]
        
        # 检查文件是否存在
        if not os.path.exists(archive_path):
            del self._cache[archive_path]
            return None
        
        # 检查文件是否被修改
        stat = os.stat(archive_path)
        current_checksum = self._calculate_checksum(
            archive_path, stat.st_size, stat.st_mtime
        )
        
        if index.checksum != current_checksum:
            # 文件已修改，删除旧索引
            del self._cache[archive_path]
            return None
        
        return index
    
    def set_index(self, archive_path: str, files: List[FileEntry]):
        """
        设置压缩包索引
        
        参数:
            archive_path: 压缩包路径
            files: 文件列表
        """
        if not os.path.exists(archive_path):
            return
        
        stat = os.stat(archive_path)
        checksum = self._calculate_checksum(
            archive_path, stat.st_size, stat.st_mtime
        )
        
        index = ArchiveIndex(
            archive_path=archive_path,
            archive_mtime=stat.st_mtime,
            archive_size=stat.st_size,
            file_count=len(files),
            files=files,
            scan_time=datetime.now().timestamp(),
            checksum=checksum
        )
        
        self._cache[archive_path] = index
    
    def clear_cache(self):
        """清空所有缓存"""
        self._cache.clear()
        if self.cache_file.exists():
            self.cache_file.unlink()
    
    def remove_index(self, archive_path: str):
        """删除指定压缩包的索引"""
        if archive_path in self._cache:
            del self._cache[archive_path]
    
    def flush(self):
        """刷新缓存到磁盘"""
        self._save_cache()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_files = sum(idx.file_count for idx in self._cache.values())
        total_size = sum(idx.archive_size for idx in self._cache.values())
        
        return {
            "压缩包数量": len(self._cache),
            "总文件数": total_files,
            "总大小": total_size,
            "缓存目录": str(self.cache_dir),
        }


# 全局缓存实例
_global_cache: Optional[IndexCache] = None


def get_global_cache() -> IndexCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = IndexCache()
    return _global_cache
