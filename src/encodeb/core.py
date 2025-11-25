from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable


def _reencode_component(name: str, src_encoding: str, dst_encoding: str) -> str:
    try:
        data = name.encode(src_encoding)
        return data.decode(dst_encoding)
    except UnicodeError:
        return name


def _build_dest_path(
    root: Path,
    dest_root: Path,
    path: Path,
    src_encoding: str,
    dst_encoding: str,
) -> Path:
    rel_parts = path.relative_to(root).parts
    new_parts = [
        _reencode_component(part, src_encoding, dst_encoding) for part in rel_parts
    ]
    return dest_root.joinpath(*new_parts)


def _iter_paths(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        yield p


def recover_tree(
    root: Path | str,
    src_encoding: str = "cp437",
    dst_encoding: str = "cp936",
) -> Path:
    base_root = Path(root)
    if not base_root.is_dir():
        raise ValueError(f"{base_root} is not a directory")

    dest_root = base_root.with_name(base_root.name + "_recovered")
    original_dest_root = dest_root
    index = 1
    while dest_root.exists():
        dest_root = original_dest_root.with_name(f"{original_dest_root.name}_{index}")
        index += 1

    for path in _iter_paths(base_root):
        dest_path = _build_dest_path(
            base_root,
            dest_root,
            path,
            src_encoding,
            dst_encoding,
        )

        if path.is_dir():
            dest_path.mkdir(parents=True, exist_ok=True)
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        final_dest = dest_path
        if final_dest.exists():
            stem = final_dest.stem
            suffix = final_dest.suffix
            i = 1
            candidate = final_dest
            while candidate.exists():
                candidate = final_dest.with_name(f"{stem}_{i}{suffix}")
                i += 1
            final_dest = candidate

        shutil.copy2(path, final_dest)

    return dest_root
