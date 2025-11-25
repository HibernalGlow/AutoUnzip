import argparse
import sys
from pathlib import Path

from encodeb.core import recover_tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover garbled file and directory names by re-encoding "
            "from a source encoding to a destination encoding and copying "
            "to a new directory."
        )
    )
    parser.add_argument(
        "root",
        type=str,
        help="Path to the directory containing garbled names.",
    )
    parser.add_argument(
        "--src-encoding",
        default="cp437",
        help="Encoding that was incorrectly used to decode the original bytes.",
    )
    parser.add_argument(
        "--dst-encoding",
        default="cp936",
        help="Encoding that should be used to decode the original bytes (e.g. cp936, cp932).",
    )

    args = parser.parse_args(argv)

    root_path = Path(args.root)
    dest_root = recover_tree(
        root=root_path,
        src_encoding=args.src_encoding,
        dst_encoding=args.dst_encoding,
    )

    print(f"Recovered files copied to: {dest_root}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())