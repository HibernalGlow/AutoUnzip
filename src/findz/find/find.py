"""File information and archive listing."""

import os
import tarfile
import zipfile
from datetime import datetime, time as time_type
from pathlib import Path
from typing import Iterator, Optional

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
    
    def is_dir(self) -> bool:
        """Check if this is a directory."""
        return self.file_type == "dir"
    
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
            else:
                return None
        
        return getter
    
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
                # Determine if it's a directory (ends with /)
                if info.filename.endswith("/"):
                    name = info.filename.rstrip("/")
                    file_type = "dir"
                else:
                    name = info.filename
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
                        archive=fullpath,
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
