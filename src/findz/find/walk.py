"""File system walking and searching."""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional

from ..filter.filter import FilterExpression
from .find import FileInfo, FindError, list_files_in_archive


class WalkParams:
    """Parameters for walking the file system."""
    
    def __init__(
        self,
        filter_expr: FilterExpression,
        follow_symlinks: bool = False,
        no_archive: bool = False,
        error_handler: Optional[Callable[[str], None]] = None,
    ):
        self.filter_expr = filter_expr
        self.follow_symlinks = follow_symlinks
        self.no_archive = no_archive
        self.error_handler = error_handler


def make_file_info(fullpath: str, stat_info: os.stat_result) -> FileInfo:
    """Create a FileInfo object from os.stat result."""
    
    # Determine file type
    if os.path.islink(fullpath):
        file_type = "link"
    elif os.path.isdir(fullpath):
        file_type = "dir"
    else:
        file_type = "file"
    
    return FileInfo(
        name=os.path.basename(fullpath),
        path=fullpath,
        mod_time=datetime.fromtimestamp(stat_info.st_mtime),
        size=stat_info.st_size,
        file_type=file_type,
    )


def fs_walk(
    root: str,
    follow_symlinks: bool,
    report: Callable[[Optional[FileInfo], Optional[Exception]], None],
) -> None:
    """Walk the file system starting from root.
    
    Args:
        root: Root directory to start walking from
        follow_symlinks: Whether to follow symbolic links
        report: Callback function to report files and errors
    """
    
    def walk_recursive(path: str, virt_path: str) -> None:
        """Recursively walk a directory."""
        
        try:
            # Use lstat to not follow symlinks initially
            stat_info = os.lstat(path)
        except Exception as e:
            report(None, FindError(path, e))
            return
        
        # Create FileInfo
        file_info = make_file_info(virt_path, stat_info)
        
        # Handle symlinks
        if file_info.file_type == "link" and follow_symlinks:
            try:
                # Resolve the symlink
                real_path = os.path.realpath(path)
                stat_info = os.stat(real_path)
                
                # Create new FileInfo with resolved info but original path
                file_info2 = make_file_info(real_path, stat_info)
                file_info = FileInfo(
                    name=file_info.name,
                    path=file_info.path,
                    mod_time=file_info2.mod_time,
                    size=file_info2.size,
                    file_type=file_info2.file_type,
                )
                
                # Update path for recursion
                path = real_path
            except Exception as e:
                report(None, FindError(path, e))
                return
        
        # Report the file/directory
        report(file_info, None)
        
        # If it's a directory, recurse into it
        if file_info.is_dir():
            try:
                entries = sorted(os.listdir(path))
            except Exception as e:
                report(None, FindError(path, e))
                return
            
            for entry in entries:
                child_path = os.path.join(path, entry)
                child_virt_path = os.path.join(virt_path, entry)
                walk_recursive(child_path, child_virt_path)
    
    walk_recursive(root, root)


def find_in(file_info: FileInfo, params: WalkParams) -> Iterator[FileInfo]:
    """Find files matching filter, including inside archives.
    
    Args:
        file_info: File to search in
        params: Search parameters
    
    Yields:
        FileInfo objects that match the filter
    """
    
    # Test if the file itself matches
    try:
        matches, error = params.filter_expr.test(file_info.context())
        if error:
            if params.error_handler:
                params.error_handler(str(error))
        elif matches:
            yield file_info
    except Exception as e:
        if params.error_handler:
            params.error_handler(f"{file_info.path}: {e}")
    
    # If it's a directory or we're not checking archives, stop here
    if file_info.is_dir() or params.no_archive:
        return
    
    # Try to list files in archive
    try:
        archive_files = list_files_in_archive(file_info.path)
        
        if archive_files:
            # Sort by path
            archive_files.sort(key=lambda f: f.path)
            
            # Test each file in the archive
            for archive_file in archive_files:
                try:
                    matches, error = params.filter_expr.test(archive_file.context())
                    if error:
                        if params.error_handler:
                            params.error_handler(str(error))
                    elif matches:
                        yield archive_file
                except Exception as e:
                    if params.error_handler:
                        params.error_handler(f"{archive_file.path}: {e}")
    
    except FindError as e:
        # Not an archive or error reading it
        if params.error_handler and "not installed" not in str(e):
            params.error_handler(str(e))
    except Exception as e:
        if params.error_handler:
            params.error_handler(f"{file_info.path}: {e}")


def walk(
    root: str,
    params: WalkParams,
) -> Iterator[FileInfo]:
    """Walk the file system and yield matching files.
    
    Args:
        root: Root directory to start from
        params: Search parameters including filter
    
    Yields:
        FileInfo objects that match the filter
    """
    
    results = []
    
    def report(file_info: Optional[FileInfo], error: Optional[Exception]) -> None:
        """Handle file or error from fs_walk."""
        if error:
            if params.error_handler:
                params.error_handler(str(error))
        elif file_info:
            # Find matching files (including in archives)
            for match in find_in(file_info, params):
                results.append(match)
    
    # Start the walk
    fs_walk(root, params.follow_symlinks, report)
    
    # Yield all results
    yield from results
