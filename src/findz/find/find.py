"""File information and archive listing."""

import os
import re
import stat
import tarfile
import zipfile
from datetime import datetime, time as time_type
from pathlib import Path
from typing import Iterator, Optional, List, Dict, Tuple

# 缓存容器统计信息: (container_path, exts_tuple) -> avg_size
_container_stats_cache: Dict[Tuple[str, Tuple[str, ...]], int] = {}

from ..filter.size import format_size
from ..filter.value import Value, number_value, text_value


class FindError(Exception):
    """Exception raised during file finding operations."""
    
    def __init__(self, path: str, error: Exception):
        self.path = path
        self.error = error
        super().__init__(f"{path}: {error}")


class FileInfo:
    """Information about a file or directory."""
    
    # 类级别标志：是否启用图片元数据读取
    _image_meta_enabled: bool = False
    
    def __init__(
        self,
        name: str,
        path: str,
        mod_time: datetime,
        size: int,
        file_type: str,
        container: str = "",
        archive: str = "",
    ):
        self.name = name
        self.path = path
        self.mod_time = mod_time
        self.size = size
        self.file_type = file_type  # "file", "dir", "link"
        self.container = container
        self.archive = archive  # "tar", "zip", "7z", "rar", or ""
        # 延迟加载的图片尺寸缓存
        self._image_dims_cache = None
        self._image_dims_loaded = False
    
    @classmethod
    def enable_image_meta(cls, enabled: bool = True):
        """启用或禁用图片元数据读取"""
        cls._image_meta_enabled = enabled
    
    def is_dir(self) -> bool:
        """Check if this is a directory."""
        return self.file_type == "dir"
    
    def _get_image_dimensions(self):
        """
        获取图片尺寸（延迟加载，带缓存）
        
        支持文件系统上的文件和压缩包内的文件
        """
        if self._image_dims_loaded:
            return self._image_dims_cache
        
        self._image_dims_loaded = True
        
        # 只在启用了图片元数据时读取
        if not FileInfo._image_meta_enabled:
            return None
        
        # 只对文件（非目录）读取
        if self.file_type != "file":
            return None
        
        try:
            # 情况1: 文件系统上的文件
            if not self.container:
                from ..filter.image_meta import get_image_dimensions_cached
                # 使用文件的修改时间作为缓存 key 的一部分
                mtime = self.mod_time.timestamp() if self.mod_time else 0
                self._image_dims_cache = get_image_dimensions_cached(self.path, mtime)
            
            # 情况2: 压缩包内的文件
            else:
                from ..filter.image_meta import get_image_dimensions_from_bytes
                
                # 从压缩包中读取文件数据
                data = self._read_from_archive()
                if data:
                    self._image_dims_cache = get_image_dimensions_from_bytes(data, self.name)
                
        except Exception:
            self._image_dims_cache = None
        
        return self._image_dims_cache
    
    def _read_from_archive(self) -> Optional[bytes]:
        """从压缩包中读取文件数据"""
        if not self.container:
            return None
        
        try:
            if self.archive == "zip":
                import zipfile
                # 打开 ZIP 文件（不指定编码，使用默认）
                with zipfile.ZipFile(self.container, 'r') as zf:
                    # 尝试直接读取（UTF-8 路径）
                    try:
                        return zf.read(self.path)
                    except KeyError:
                        # 如果失败，尝试将 UTF-8 路径转换回原始编码
                        # 因为 list_files_in_zip 做了 cp437->gbk 的转换
                        # 这里需要反向转换：utf-8->gbk->cp437
                        try:
                            original_path = self.path.encode('gbk').decode('cp437')
                            return zf.read(original_path)
                        except (KeyError, UnicodeDecodeError, UnicodeEncodeError):
                            pass
                        
                        # 如果还是失败，尝试遍历 ZIP 查找匹配的文件
                        # 对每个 ZIP 内的文件名进行相同的编码转换，看是否匹配
                        for info in zf.infolist():
                            filename = info.filename
                            try:
                                if not (info.flag_bits & 0x800):
                                    # 尝试 cp437->gbk 转换
                                    try:
                                        filename = info.filename.encode('cp437').decode('gbk')
                                    except (UnicodeDecodeError, UnicodeEncodeError):
                                        try:
                                            filename = info.filename.encode('cp437').decode('utf-8')
                                        except (UnicodeDecodeError, UnicodeEncodeError):
                                            pass
                            except Exception:
                                pass
                            
                            if filename == self.path:
                                return zf.read(info.filename)
                        
                        return None
            
            elif self.archive == "tar":
                import tarfile
                with tarfile.open(self.container, 'r:*') as tf:
                    member = tf.getmember(self.path)
                    f = tf.extractfile(member)
                    return f.read() if f else None
            
            elif self.archive == "7z":
                import py7zr
                with py7zr.SevenZipFile(self.container, 'r') as szf:
                    data = szf.read([self.path])
                    return data.get(self.path)
            
            elif self.archive == "rar":
                import rarfile
                with rarfile.RarFile(self.container, 'r') as rf:
                    return rf.read(self.path)
        
        except Exception:
            return None
        
        return None
    
    def context(self) -> callable:
        """Return a function that can get file properties by name."""
        
        def getter(name: str) -> Optional[Value]:
            name_lower = name.lower()
            
            if name_lower == "name":
                return text_value(self.name)
            elif name_lower == "path":
                return text_value(self.path)
            elif name_lower == "size":
                return number_value(self.size)
            elif name_lower == "date":
                return text_value(self.mod_time.strftime("%Y-%m-%d"))
            elif name_lower == "time":
                return text_value(self.mod_time.strftime("%H:%M:%S"))
            elif name_lower == "ext":
                ext = os.path.splitext(self.name)[1]
                return text_value(ext.lstrip("."))
            elif name_lower == "ext2":
                return text_value(self._get_ext2())
            elif name_lower == "type":
                return text_value(self.file_type)
            elif name_lower == "container":
                return text_value(self.container)
            elif name_lower == "archive":
                return text_value(self.archive)
            elif name_lower == "today":
                return text_value(datetime.now().strftime("%Y-%m-%d"))
            elif name_lower in ("mo", "tu", "we", "th", "fr", "sa", "su"):
                return self._get_last_weekday(name_lower)
            # ========== 图片元数据字段 ==========
            elif name_lower == "width":
                dims = self._get_image_dimensions()
                return number_value(dims.width) if dims else None
            elif name_lower == "height":
                dims = self._get_image_dimensions()
                return number_value(dims.height) if dims else None
            elif name_lower == "resolution":
                dims = self._get_image_dimensions()
                return text_value(dims.resolution) if dims else None
            elif name_lower == "megapixels":
                dims = self._get_image_dimensions()
                return number_value(int(dims.megapixels * 100) / 100) if dims else None
            elif name_lower == "aspect":
                dims = self._get_image_dimensions()
                return number_value(int(dims.aspect_ratio * 100) / 100) if dims else None
            
            # ========== 容器统计字段 ==========
            elif name_lower == "avg_img_size":
                # 图片默认扩展名
                img_exts = ("jpg", "jpeg", "png", "gif", "webp", "bmp", "svg")
                return number_value(self._get_avg_size_of_container(img_exts))
            elif name_lower == "avg_vid_size":
                # 视频默认扩展名
                vid_exts = ("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm")
                return number_value(self._get_avg_size_of_container(vid_exts))
            elif name_lower.startswith("avg_size_"):
                # 动态指定扩展名，如 avg_size_jpg_png
                exts = tuple(name_lower[9:].split("_"))
                return number_value(self._get_avg_size_of_container(exts))
            else:
                return None
        
        return getter

    def _get_avg_size_of_container(self, exts: tuple) -> int:
        """
        获取当前文件所在容器（或自身，若是目录/压缩包）中指定格式文件的平均大小
        """
        # 1. 确定搜索目标路径
        container_path = self.container or ""
        
        # 如果当前文件本身就是压缩包或目录，且我们想查它内部的平均值
        if not container_path:
            if self.file_type == "dir":
                container_path = self.path
            elif self.archive or self.name.lower().endswith((".zip", ".7z", ".rar", ".tar")):
                container_path = self.path
        
        if not container_path:
            return 0
            
        # 2. 检查缓存
        exts_key = tuple(sorted(list(exts)))
        cache_key = (container_path, exts_key)
        
        if cache_key in _container_stats_cache:
            return _container_stats_cache[cache_key]
            
        # 3. 获取内容并统计
        try:
            total_size = 0
            count = 0
            
            if os.path.isdir(container_path):
                # 目录：仅列出顶层文件（暂不支持递归以保证性能）
                for name in os.listdir(container_path):
                    if name.split('.')[-1].lower() in exts:
                        p = os.path.join(container_path, name)
                        try:
                            st = os.stat(p)
                            if stat.S_ISREG(st.st_mode):
                                total_size += st.st_size
                                count += 1
                        except OSError:
                            pass
            else:
                # 压缩包
                files = list_files_in_archive(container_path)
                if files:
                    for f in files:
                        if f.name.split('.')[-1].lower() in exts:
                            total_size += f.size
                            count += 1
            
            avg_size = int(total_size / count) if count > 0 else 0
            _container_stats_cache[cache_key] = avg_size
            return avg_size
            
        except Exception:
            _container_stats_cache[cache_key] = 0
            return 0
    
    def _get_ext2(self) -> str:
        """Get the two-part extension (e.g., 'tar.gz')."""
        parts = self.name.split(".")
        if len(parts) >= 3:
            return ".".join(parts[-2:])
        elif len(parts) == 2:
            return parts[-1]
        return ""
    
    def _get_last_weekday(self, weekday: str) -> Value:
        """Get the date of the last occurrence of a weekday."""
        from datetime import timedelta
        
        weekday_map = {
            "mo": 0,  # Monday
            "tu": 1,  # Tuesday
            "we": 2,  # Wednesday
            "th": 3,  # Thursday
            "fr": 4,  # Friday
            "sa": 5,  # Saturday
            "su": 6,  # Sunday
        }
        
        target_weekday = weekday_map[weekday]
        now = datetime.now()
        current_weekday = now.weekday()
        
        # Calculate days to subtract
        days_back = current_weekday - target_weekday
        if days_back <= 0:
            days_back += 7
        
        target_date = now - timedelta(days=days_back)
        return text_value(target_date.strftime("%Y-%m-%d"))


def list_files_in_tar(fullpath: str) -> list[FileInfo]:
    """List files inside a tar archive (including .tar.gz, .tar.bz2, .tar.xz).
    
    Args:
        fullpath: Path to the tar file
    
    Returns:
        List of FileInfo objects for files in the archive
    
    Raises:
        FindError: If there's an error reading the archive
    """
    try:
        with tarfile.open(fullpath, "r:*") as tar:
            files = []
            for member in tar.getmembers():
                if member.isfile():
                    file_type = "file"
                elif member.isdir():
                    file_type = "dir"
                elif member.issym() or member.islnk():
                    file_type = "link"
                else:
                    continue
                
                files.append(
                    FileInfo(
                        name=os.path.basename(member.name),
                        path=member.name,
                        mod_time=datetime.fromtimestamp(member.mtime),
                        size=member.size,
                        file_type=file_type,
                        container=fullpath,
                        archive=fullpath,
                    )
                )
            return files
    except Exception as e:
        raise FindError(fullpath, e)


def list_files_in_zip(fullpath: str) -> list[FileInfo]:
    """List files inside a zip archive.
    
    Args:
        fullpath: Path to the zip file
    
    Returns:
        List of FileInfo objects for files in the archive
    
    Raises:
        FindError: If there's an error reading the archive
    """
    try:
        with zipfile.ZipFile(fullpath, "r") as zf:
            files = []
            for info in zf.infolist():
                # 处理文件名编码问题
                # ZIP 文件中的中文文件名可能使用 GBK/CP936 编码
                filename = info.filename
                try:
                    # 如果文件名包含非 ASCII 字符且看起来像乱码，尝试重新解码
                    if info.flag_bits & 0x800:
                        # UTF-8 标志位已设置，文件名已经是 UTF-8
                        pass
                    else:
                        # 尝试将 CP437 编码的字节重新解码为 GBK
                        try:
                            filename = info.filename.encode('cp437').decode('gbk')
                        except (UnicodeDecodeError, UnicodeEncodeError):
                            # 如果失败，尝试其他编码
                            try:
                                filename = info.filename.encode('cp437').decode('utf-8')
                            except (UnicodeDecodeError, UnicodeEncodeError):
                                # 保持原样
                                pass
                except Exception:
                    pass
                
                # Determine if it's a directory (ends with /)
                if filename.endswith("/"):
                    name = filename.rstrip("/")
                    file_type = "dir"
                else:
                    name = filename
                    file_type = "file"
                
                # Get modification time
                mod_time = datetime(*info.date_time)
                
                files.append(
                    FileInfo(
                        name=os.path.basename(name),
                        path=name,
                        mod_time=mod_time,
                        size=info.file_size,
                        file_type=file_type,
                        container=fullpath,
                        archive="zip",
                    )
                )
            return files
    except Exception as e:
        raise FindError(fullpath, e)


def list_files_in_7z(fullpath: str) -> list[FileInfo]:
    """List files inside a 7z archive.
    
    Args:
        fullpath: Path to the 7z file
    
    Returns:
        List of FileInfo objects for files in the archive
    
    Raises:
        FindError: If there's an error reading the archive
    """
    try:
        import py7zr
        
        with py7zr.SevenZipFile(fullpath, "r") as szf:
            files = []
            for name, info in szf.list():
                # Determine if it's a directory
                file_type = "dir" if info.is_directory else "file"
                
                files.append(
                    FileInfo(
                        name=os.path.basename(name),
                        path=name,
                        mod_time=info.creationtime or datetime.now(),
                        size=info.uncompressed,
                        file_type=file_type,
                        container=fullpath,
                        archive=fullpath,
                    )
                )
            return files
    except ImportError:
        raise FindError(fullpath, Exception("py7zr not installed. Install with: pip install py7zr"))
    except Exception as e:
        raise FindError(fullpath, e)


def list_files_in_rar(fullpath: str) -> list[FileInfo]:
    """List files inside a rar archive.
    
    Args:
        fullpath: Path to the rar file
    
    Returns:
        List of FileInfo objects for files in the archive
    
    Raises:
        FindError: If there's an error reading the archive
    """
    try:
        import rarfile
        
        with rarfile.RarFile(fullpath, "r") as rf:
            files = []
            for info in rf.infolist():
                file_type = "dir" if info.isdir() else "file"
                
                files.append(
                    FileInfo(
                        name=os.path.basename(info.filename),
                        path=info.filename,
                        mod_time=info.date_time,
                        size=info.file_size,
                        file_type=file_type,
                        container=fullpath,
                        archive=fullpath,
                    )
                )
            return files
    except ImportError:
        raise FindError(fullpath, Exception("rarfile not installed. Install with: pip install rarfile"))
    except Exception as e:
        raise FindError(fullpath, e)


def list_files_in_archive(fullpath: str) -> Optional[list[FileInfo]]:
    """List files in an archive, detecting type from extension.
    
    Args:
        fullpath: Path to the archive file
    
    Returns:
        List of FileInfo objects, or None if not an archive
    
    Raises:
        FindError: If there's an error reading the archive
    """
    lower = fullpath.lower()
    
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
        return list_files_in_tar(fullpath)
    elif lower.endswith(".zip"):
        return list_files_in_zip(fullpath)
    elif lower.endswith(".7z"):
        return list_files_in_7z(fullpath)
    elif lower.endswith(".rar"):
        return list_files_in_rar(fullpath)
    else:
        return None

# Export field names for CSV output
FIELDS = [
    "name",
    "path",
    "container",
    "size",
    "date",
    "time",
    "ext",
    "ext2",
    "type",
    "archive",
]

# 图片元数据字段（需要 --with-image-meta 启用）
IMAGE_FIELDS = [
    "width",
    "height", 
    "resolution",
    "megapixels",
    "aspect",
]
