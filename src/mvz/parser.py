"""Parse findz output format into archive path and internal path."""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, TextIO


@dataclass
class ArchiveEntry:
    """Represents a file entry inside an archive."""
    archive_path: str      # Path to the archive file
    internal_path: str     # Path inside the archive
    raw_line: str          # Original line from input
    
    @property
    def archive_name(self) -> str:
        """Get archive filename without extension."""
        return Path(self.archive_path).stem
    
    @property
    def archive_ext(self) -> str:
        """Get archive extension (lowercase, without dot)."""
        return Path(self.archive_path).suffix.lstrip('.').lower()
    
    @property
    def internal_name(self) -> str:
        """Get internal file name without path."""
        return Path(self.internal_path).name
    
    @property
    def internal_ext(self) -> str:
        """Get internal file extension (lowercase, without dot)."""
        return Path(self.internal_path).suffix.lstrip('.').lower()


def parse_line(line: str, separator: str = "//") -> Optional[ArchiveEntry]:
    """Parse a single line from findz output.
    
    Args:
        line: A line in format "archive_path//internal_path" or just a path
        separator: Separator between archive and internal path (default: //)
    
    Returns:
        ArchiveEntry if successfully parsed, None if not an archive entry
    """
    line = line.strip()
    if not line:
        return None
    
    # Check if this is a long format line (date size path)
    # Example: "2025-01-15 10:30:45      1.5K D:\path\archive.zip//file.txt"
    long_format_match = re.match(
        r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+[\d.]+[BKMGT]?\s+(.+)$',
        line
    )
    if long_format_match:
        path_part = long_format_match.group(1)
    else:
        path_part = line
    
    # Split by separator
    if separator in path_part:
        parts = path_part.split(separator, 1)
        if len(parts) == 2:
            archive_path, internal_path = parts
            return ArchiveEntry(
                archive_path=archive_path.strip(),
                internal_path=internal_path.strip(),
                raw_line=line
            )
    
    # Not an archive entry (regular file path)
    return None


def parse_input(
    input_source: Optional[Iterator[str]] = None,
    separator: str = "//",
    skip_non_archive: bool = True,
) -> Iterator[ArchiveEntry]:
    """Parse findz output from stdin or file.
    
    Args:
        input_source: Iterator yielding lines (default: stdin)
        separator: Separator between archive and internal path
        skip_non_archive: If True, skip lines that are not archive entries
    
    Yields:
        ArchiveEntry objects for each valid archive entry
    """
    source = input_source or sys.stdin
    
    for line in source:
        entry = parse_line(line, separator)
        if entry:
            yield entry
        elif not skip_non_archive:
            # For non-archive files, we could handle them differently
            # but for now we skip them
            pass


def parse_lines(lines: List[str], separator: str = "//") -> List[ArchiveEntry]:
    """Parse a list of lines into ArchiveEntry objects.
    
    Args:
        lines: List of lines from findz output
        separator: Separator between archive and internal path
    
    Returns:
        List of ArchiveEntry objects
    """
    entries = []
    for line in lines:
        entry = parse_line(line, separator)
        if entry:
            entries.append(entry)
    return entries


def group_by_archive(entries: List[ArchiveEntry]) -> dict[str, List[ArchiveEntry]]:
    """Group entries by archive path.
    
    Args:
        entries: List of ArchiveEntry objects
    
    Returns:
        Dictionary mapping archive paths to list of entries
    """
    groups: dict[str, List[ArchiveEntry]] = {}
    for entry in entries:
        if entry.archive_path not in groups:
            groups[entry.archive_path] = []
        groups[entry.archive_path].append(entry)
    return groups
