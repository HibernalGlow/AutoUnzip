"""mvz - Archive file manipulation CLI tool.

Companion tool to findz for manipulating files inside archives.
Supports rename, delete, extract operations on ZIP/7Z/RAR archives.
"""

from .cli import app

__version__ = "0.1.0"
__all__ = ["app"]
