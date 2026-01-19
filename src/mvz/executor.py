"""Execute archive operations using 7z CLI."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .parser import ArchiveEntry


@dataclass
class ExecutionResult:
    """Result of an archive operation."""
    success: bool
    message: str
    archive_path: str
    internal_paths: List[str]
    command: Optional[str] = None


def find_7z() -> Optional[str]:
    """Find 7z executable in PATH or common locations.
    
    Returns:
        Path to 7z executable, or None if not found
    """
    # Check PATH first
    sz = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if sz:
        return sz
    
    # Common Windows locations
    common_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\7-Zip\7z.exe"),
    ]
    
    for path in common_paths:
        if os.path.isfile(path):
            return path
    
    return None


def run_7z(args: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
    """Run 7z command with given arguments.
    
    Args:
        args: List of arguments to pass to 7z
        capture_output: Whether to capture stdout/stderr
    
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    sz_path = find_7z()
    if not sz_path:
        return (-1, "", "7z not found. Please install 7-Zip and add to PATH.")
    
    cmd = [sz_path] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        return (result.returncode, result.stdout, result.stderr)
    except Exception as e:
        return (-1, "", str(e))


def delete_files(
    archive_path: str,
    internal_paths: List[str],
    dry_run: bool = True,
) -> ExecutionResult:
    """Delete files from an archive.
    
    Args:
        archive_path: Path to the archive
        internal_paths: List of internal paths to delete
        dry_run: If True, only show what would be done
    
    Returns:
        ExecutionResult with operation status
    """
    if not os.path.isfile(archive_path):
        return ExecutionResult(
            success=False,
            message=f"Archive not found: {archive_path}",
            archive_path=archive_path,
            internal_paths=internal_paths,
        )
    
    # Build 7z delete command: 7z d archive.zip file1 file2 ...
    args = ["d", archive_path] + internal_paths
    cmd_str = f"7z d \"{archive_path}\" " + " ".join(f'"{p}"' for p in internal_paths)
    
    if dry_run:
        return ExecutionResult(
            success=True,
            message=f"[DRY RUN] Would delete {len(internal_paths)} file(s)",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )
    
    retcode, stdout, stderr = run_7z(args)
    
    if retcode == 0:
        return ExecutionResult(
            success=True,
            message=f"Deleted {len(internal_paths)} file(s) from {Path(archive_path).name}",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )
    else:
        return ExecutionResult(
            success=False,
            message=f"Failed to delete: {stderr or stdout}",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )


def rename_file(
    archive_path: str,
    old_path: str,
    new_path: str,
    dry_run: bool = True,
) -> ExecutionResult:
    """Rename a file inside an archive.
    
    Args:
        archive_path: Path to the archive
        old_path: Current internal path
        new_path: New internal path
        dry_run: If True, only show what would be done
    
    Returns:
        ExecutionResult with operation status
    """
    if not os.path.isfile(archive_path):
        return ExecutionResult(
            success=False,
            message=f"Archive not found: {archive_path}",
            archive_path=archive_path,
            internal_paths=[old_path],
        )
    
    # Build 7z rename command: 7z rn archive.zip old_name new_name
    args = ["rn", archive_path, old_path, new_path]
    cmd_str = f'7z rn "{archive_path}" "{old_path}" "{new_path}"'
    
    if dry_run:
        return ExecutionResult(
            success=True,
            message=f"[DRY RUN] Would rename: {old_path} -> {new_path}",
            archive_path=archive_path,
            internal_paths=[old_path],
            command=cmd_str,
        )
    
    retcode, stdout, stderr = run_7z(args)
    
    if retcode == 0:
        return ExecutionResult(
            success=True,
            message=f"Renamed: {old_path} -> {new_path}",
            archive_path=archive_path,
            internal_paths=[old_path],
            command=cmd_str,
        )
    else:
        return ExecutionResult(
            success=False,
            message=f"Failed to rename: {stderr or stdout}",
            archive_path=archive_path,
            internal_paths=[old_path],
            command=cmd_str,
        )


def extract_files(
    archive_path: str,
    internal_paths: List[str],
    output_dir: str,
    dry_run: bool = True,
    flatten: bool = False,
) -> ExecutionResult:
    """Extract specific files from an archive.
    
    Args:
        archive_path: Path to the archive
        internal_paths: List of internal paths to extract
        output_dir: Directory to extract files to
        dry_run: If True, only show what would be done
        flatten: If True, extract all files to output_dir without subdirectories
    
    Returns:
        ExecutionResult with operation status
    """
    if not os.path.isfile(archive_path):
        return ExecutionResult(
            success=False,
            message=f"Archive not found: {archive_path}",
            archive_path=archive_path,
            internal_paths=internal_paths,
        )
    
    # Use 'e' for flatten (extract without paths), 'x' for full paths
    extract_cmd = "e" if flatten else "x"
    
    # Build 7z extract command: 7z x archive.zip -o"output_dir" file1 file2 ...
    args = [extract_cmd, archive_path, f"-o{output_dir}", "-y"] + internal_paths
    cmd_str = f'7z {extract_cmd} "{archive_path}" -o"{output_dir}" -y ' + " ".join(f'"{p}"' for p in internal_paths)
    
    if dry_run:
        return ExecutionResult(
            success=True,
            message=f"[DRY RUN] Would extract {len(internal_paths)} file(s) to {output_dir}",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )
    
    # Create output directory if needed
    os.makedirs(output_dir, exist_ok=True)
    
    retcode, stdout, stderr = run_7z(args)
    
    if retcode == 0:
        return ExecutionResult(
            success=True,
            message=f"Extracted {len(internal_paths)} file(s) to {output_dir}",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )
    else:
        return ExecutionResult(
            success=False,
            message=f"Failed to extract: {stderr or stdout}",
            archive_path=archive_path,
            internal_paths=internal_paths,
            command=cmd_str,
        )


def batch_rename(
    archive_path: str,
    rename_pairs: List[Tuple[str, str]],
    dry_run: bool = True,
) -> ExecutionResult:
    """Batch rename files inside an archive.
    
    Args:
        archive_path: Path to the archive
        rename_pairs: List of (old_path, new_path) tuples
        dry_run: If True, only show what would be done
    
    Returns:
        ExecutionResult with operation status
    """
    if not os.path.isfile(archive_path):
        return ExecutionResult(
            success=False,
            message=f"Archive not found: {archive_path}",
            archive_path=archive_path,
            internal_paths=[p[0] for p in rename_pairs],
        )
    
    # Build 7z rename command: 7z rn archive.zip old1 new1 old2 new2 ...
    args = ["rn", archive_path]
    for old, new in rename_pairs:
        args.extend([old, new])
    
    cmd_parts = [f'"{old}" "{new}"' for old, new in rename_pairs]
    cmd_str = f'7z rn "{archive_path}" ' + " ".join(cmd_parts)
    
    if dry_run:
        return ExecutionResult(
            success=True,
            message=f"[DRY RUN] Would rename {len(rename_pairs)} file(s)",
            archive_path=archive_path,
            internal_paths=[p[0] for p in rename_pairs],
            command=cmd_str,
        )
    
    retcode, stdout, stderr = run_7z(args)
    
    if retcode == 0:
        return ExecutionResult(
            success=True,
            message=f"Renamed {len(rename_pairs)} file(s) in {Path(archive_path).name}",
            archive_path=archive_path,
            internal_paths=[p[0] for p in rename_pairs],
            command=cmd_str,
        )
    else:
        return ExecutionResult(
            success=False,
            message=f"Failed to rename: {stderr or stdout}",
            archive_path=archive_path,
            internal_paths=[p[0] for p in rename_pairs],
            command=cmd_str,
        )
