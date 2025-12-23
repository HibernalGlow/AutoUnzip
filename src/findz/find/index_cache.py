"""
压缩包索引缓存模块
用于加速大规模压缩包搜索，避免重复扫描

优化策略：
1. 使用 SQLite 替代 JSON 存储，支持增量更新
2. 延迟加载：只在需要时加载特定压缩包的索引
3. 批量写入：减少磁盘 I/O
"""

import os
import sqlite3
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass
from contextlib import contextmanager


@dataclass
class FileEntry:
    """文件条目信息"""
    name: str  # 文件名
    path: str  # 完整路径
    size: int  # 文件大小
    mtime: float  # 修改时间戳
    is_archive: bool  # 是否为压缩包
    ext: str  # 扩展名
    file_type: str = "file"  # 文件类型: file/dir/link
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
    checksum: str  # 压缩包校验和


class IndexCache:
    """
    索引缓存管理器（SQLite 版本）
    
    使用 SQLite 存储索引，支持：
    - 增量更新：只更新变化的压缩包
    - 延迟加载：按需加载索引
    - 并发安全：支持多线程访问
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = os.path.join(Path.home(), ".findz_cache")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "archive_index.db"
        
        # 线程本地存储，每个线程一个连接
        self._local = threading.local()
        
        # 待写入缓冲区
        self._write_buffer: List[tuple] = []
        self._buffer_lock = threading.Lock()
        self._buffer_size = 1000  # 每 1000 条写入一次
        
        # 初始化数据库
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA cache_size=10000")
        return self._local.conn
    
    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS archives (
                path TEXT PRIMARY KEY,
                mtime REAL,
                size INTEGER,
                file_count INTEGER,
                scan_time REAL,
                checksum TEXT
            );
            
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_path TEXT,
                name TEXT,
                path TEXT,
                size INTEGER,
                mtime REAL,
                is_archive INTEGER,
                ext TEXT,
                file_type TEXT DEFAULT 'file',
                FOREIGN KEY (archive_path) REFERENCES archives(path)
            );
            
            CREATE INDEX IF NOT EXISTS idx_files_archive ON files(archive_path);
            CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
        """)
        conn.commit()
    
    def _calculate_checksum(self, archive_path: str, size: int, mtime: float) -> str:
        """计算压缩包校验和"""
        data = f"{archive_path}:{size}:{mtime}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def get_index(self, archive_path: str) -> Optional[ArchiveIndex]:
        """获取压缩包索引（延迟加载文件列表）"""
        if not os.path.exists(archive_path):
            return None
        
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT mtime, size, file_count, scan_time, checksum FROM archives WHERE path = ?",
            (archive_path,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        mtime, size, file_count, scan_time, checksum = row
        
        # 检查文件是否被修改
        try:
            stat = os.stat(archive_path)
            current_checksum = self._calculate_checksum(
                archive_path, stat.st_size, stat.st_mtime
            )
            
            if checksum != current_checksum:
                # 文件已修改，删除旧索引
                self.remove_index(archive_path)
                return None
        except OSError:
            return None
        
        # 加载文件列表
        cursor = conn.execute(
            "SELECT name, path, size, mtime, is_archive, ext, file_type FROM files WHERE archive_path = ?",
            (archive_path,)
        )
        
        files = [
            FileEntry(
                name=r[0], path=r[1], size=r[2], mtime=r[3],
                is_archive=bool(r[4]), ext=r[5], file_type=r[6] or 'file',
                archive_path=archive_path
            )
            for r in cursor.fetchall()
        ]
        
        return ArchiveIndex(
            archive_path=archive_path,
            archive_mtime=mtime,
            archive_size=size,
            file_count=file_count,
            files=files,
            scan_time=scan_time,
            checksum=checksum
        )
    
    def set_index(self, archive_path: str, files: List[FileEntry]):
        """设置压缩包索引（批量写入）"""
        if not os.path.exists(archive_path):
            return
        
        try:
            stat = os.stat(archive_path)
        except OSError:
            return
        
        checksum = self._calculate_checksum(
            archive_path, stat.st_size, stat.st_mtime
        )
        
        conn = self._get_conn()
        
        # 删除旧数据
        conn.execute("DELETE FROM files WHERE archive_path = ?", (archive_path,))
        conn.execute("DELETE FROM archives WHERE path = ?", (archive_path,))
        
        # 插入压缩包信息
        conn.execute(
            "INSERT INTO archives (path, mtime, size, file_count, scan_time, checksum) VALUES (?, ?, ?, ?, ?, ?)",
            (archive_path, stat.st_mtime, stat.st_size, len(files), datetime.now().timestamp(), checksum)
        )
        
        # 批量插入文件
        conn.executemany(
            "INSERT INTO files (archive_path, name, path, size, mtime, is_archive, ext, file_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(archive_path, f.name, f.path, f.size, f.mtime, int(f.is_archive), f.ext, f.file_type) for f in files]
        )
        
        conn.commit()
    
    def remove_index(self, archive_path: str):
        """删除指定压缩包的索引"""
        conn = self._get_conn()
        conn.execute("DELETE FROM files WHERE archive_path = ?", (archive_path,))
        conn.execute("DELETE FROM archives WHERE path = ?", (archive_path,))
        conn.commit()
    
    def clear_cache(self):
        """清空所有缓存"""
        conn = self._get_conn()
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM archives")
        conn.commit()
    
    def flush(self):
        """刷新缓存（SQLite 自动管理，这里只是确保提交）"""
        try:
            conn = self._get_conn()
            conn.commit()
        except:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        conn = self._get_conn()
        
        archive_count = conn.execute("SELECT COUNT(*) FROM archives").fetchone()[0]
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        total_size = conn.execute("SELECT COALESCE(SUM(size), 0) FROM archives").fetchone()[0]
        
        return {
            "压缩包数量": archive_count,
            "总文件数": file_count,
            "总大小": total_size,
            "缓存目录": str(self.cache_dir),
            "数据库大小": os.path.getsize(self.db_path) if self.db_path.exists() else 0,
        }
    
    def iter_files(self, archive_path: str) -> Iterator[FileEntry]:
        """迭代获取文件（内存友好）"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT name, path, size, mtime, is_archive, ext FROM files WHERE archive_path = ?",
            (archive_path,)
        )
        
        for r in cursor:
            yield FileEntry(
                name=r[0], path=r[1], size=r[2], mtime=r[3],
                is_archive=bool(r[4]), ext=r[5], archive_path=archive_path
            )


# 全局缓存实例
_global_cache: Optional[IndexCache] = None


def get_global_cache() -> IndexCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = IndexCache()
    return _global_cache
