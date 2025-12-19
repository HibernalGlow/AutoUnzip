from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import Iterable

SUSPICIOUS_CHARS = set(
    "╘╙═╝║╧╞╫╔╚┌┐└┘├┤┬┴┼▓█▐▌▀▄╔╦╩╠╬"
)


class Strategy(str, Enum):
    """修改策略"""
    REPLACE = "replace"  # 原地重命名
    COPY = "copy"  # 复制到新目录


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


def preview_mappings(
    root: Path | str,
    src_encoding: str = "cp437",
    dst_encoding: str = "cp936",
    limit: int | None = 50,
) -> list[tuple[Path, Path]]:
    base_root = Path(root)
    if not base_root.is_dir():
        raise ValueError(f"{base_root} is not a directory")

    results: list[tuple[Path, Path]] = []

    for path in _iter_paths(base_root):
        dest_path = _build_dest_path(
            base_root,
            base_root,
            path,
            src_encoding,
            dst_encoding,
        )

        if path.name != dest_path.name:
            results.append((path, dest_path))
            if limit is not None and len(results) >= limit:
                break

    return results


def preview_file(
    path: Path | str,
    src_encoding: str = "cp437",
    dst_encoding: str = "cp936",
) -> list[tuple[Path, Path]]:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"{p} is not a file")

    new_name = _reencode_component(p.name, src_encoding, dst_encoding)
    if new_name == p.name:
        return []

    return [(p, p.with_name(new_name))]


def is_suspicious_name(name: str) -> bool:
    return any(ch in SUSPICIOUS_CHARS for ch in name)


def find_suspicious(
    root: Path | str,
    include_files: bool = True,
    include_dirs: bool = True,
    limit: int | None = 200,
) -> list[Path]:
    base_root = Path(root)
    if not base_root.exists():
        raise ValueError(f"{base_root} does not exist")

    results: list[Path] = []

    if base_root.is_file():
        if include_files and is_suspicious_name(base_root.name):
            results.append(base_root)
        return results

    for p in _iter_paths(base_root):
        if p.is_dir() and not include_dirs:
            continue
        if p.is_file() and not include_files:
            continue
        if is_suspicious_name(p.name):
            results.append(p)
            if limit is not None and len(results) >= limit:
                break

    return results


def recover_tree(
    root: Path | str,
    src_encoding: str = "cp437",
    dst_encoding: str = "cp936",
    strategy: Strategy = Strategy.REPLACE,
) -> Path:
    base_root = Path(root)
    if not base_root.is_dir():
        raise ValueError(f"{base_root} is not a directory")

    if strategy == Strategy.COPY:
        return _recover_tree_copy(base_root, src_encoding, dst_encoding)
    else:
        return _recover_tree_replace(base_root, src_encoding, dst_encoding)


def _recover_tree_copy(
    base_root: Path,
    src_encoding: str,
    dst_encoding: str,
) -> Path:
    """复制到新目录"""
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


def _recover_tree_replace(
    base_root: Path,
    src_encoding: str,
    dst_encoding: str,
) -> Path:
    """原地重命名，从最深层开始处理避免路径失效"""
    # 收集所有需要重命名的路径
    renames: list[tuple[Path, str]] = []

    for path in _iter_paths(base_root):
        new_name = _reencode_component(path.name, src_encoding, dst_encoding)
        if new_name != path.name:
            renames.append((path, new_name))

    # 按路径深度降序排序，先处理深层路径
    renames.sort(key=lambda x: len(x[0].parts), reverse=True)

    for path, new_name in renames:
        if not path.exists():
            # 父目录可能已被重命名，跳过
            continue

        dest_path = path.with_name(new_name)

        # 处理目标已存在的情况
        final_dest = dest_path
        if final_dest.exists() and final_dest != path:
            stem = final_dest.stem
            suffix = final_dest.suffix
            i = 1
            candidate = final_dest
            while candidate.exists():
                candidate = final_dest.with_name(f"{stem}_{i}{suffix}")
                i += 1
            final_dest = candidate

        path.rename(final_dest)

    return base_root


def recover_file(
    path: Path | str,
    src_encoding: str = "cp437",
    dst_encoding: str = "cp936",
    strategy: Strategy = Strategy.REPLACE,
) -> Path:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"{p} is not a file")

    new_name = _reencode_component(p.name, src_encoding, dst_encoding)
    if new_name == p.name:
        return p

    dest_path = p.with_name(new_name)

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

    if strategy == Strategy.COPY:
        shutil.copy2(p, final_dest)
    else:
        p.rename(final_dest)

    return final_dest
