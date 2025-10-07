"""findz - A Python port of zfind for searching files with SQL-like WHERE syntax.

Search for files, including inside tar, zip, 7z and rar archives.
"""

__version__ = "0.1.0"
__author__ = "findz contributors"

from .find.find import FileInfo
from .filter.filter import create_filter

__all__ = ["FileInfo", "create_filter"]
