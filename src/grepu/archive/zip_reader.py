from __future__ import annotations
import zipfile
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ZipEntry:
    name: str
    is_dir: bool
    size: int


def iter_zip_entries(path: str | Path):
    p = Path(path)
    with zipfile.ZipFile(p) as zf:
        for zinfo in zf.infolist():
            # zipfile 在 Python 中已经把文件名按规范位/编码处理为 str；我们不二次猜测编码。
            raw_name = zinfo.filename
            yield ZipEntry(
                name=raw_name,
                is_dir=raw_name.endswith("/"),
                size=zinfo.file_size,
            )
