#!/usr/bin/env python3
"""
Demo script: compare ugrep vs ripgrep (rg) using Python subprocess on Windows (pwsh) or any shell.

Creates a small demo tree, then runs a series of search commands with both
tools and prints labeled outputs so you can compare behavior and flags.

Usage: run in pwsh or cmd: python scripts\compare_ugrep_rg.py

This script will NOT modify files outside the demo folder.
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path
try:
    from rich.console import Console
    from rich.panel import Panel
except Exception:  # rich may be missing; fall back to simple prints
    Console = None  # type: ignore
    Panel = None  # type: ignore
import zipfile

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / 'demo_data'


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def write_demo_files(root: Path):
    if root.exists():
        shutil.rmtree(root)
    ensure_dir(root)
    print(f"Creating demo files under: {root}\n")

    (root / 'file1.txt').write_text('\n'.join([
        'Hello world',
        'This file mentions avif and AVIF.',
        'Line with Avif in mixed case',
        'Another line with hello',
    ]), encoding='utf-8')

    (root / 'file2.log').write_text('\n'.join([
        'Log start',
        'no image here',
        'avif appears here too',
    ]), encoding='utf-8')

    sub = root / 'sub'
    ensure_dir(sub)
    (sub / 'note.md').write_text('\n'.join([
        '# Notes',
        'A markdown file that does not mention the magic word.'
    ]), encoding='utf-8')

    (root / 'space file.txt').write_text('\n'.join([
        'a file whose name contains spaces',
        'it mentions avif once',
    ]), encoding='utf-8')

    # small binary file
    (root / 'binary.bin').write_bytes(bytes(range(256)))

    # zip containing the sub files
    zip_path = root / 'sample.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sub.rglob('*'):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(root)))


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def run_cmd(cmd, *, check=False, capture_output=True, text=True):
    try:
        completed = subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
        return completed.returncode, completed.stdout, completed.stderr
    except FileNotFoundError:
        return 127, '', f"command not found: {cmd[0]}"
    except subprocess.CalledProcessError as e:
        # shouldn't happen because check=False normally
        return e.returncode, getattr(e, 'output', ''), getattr(e, 'stderr', str(e))


def print_block(title: str, cmd, *, show_cmd=True, raw_bytes=False):
    # Use rich if available for nicer colored output, otherwise fallback to prints
    code, out, err = run_cmd(cmd)
    if Console is not None:
        console = Console()
        console.rule(f"{title}")
        if show_cmd:
            console.print(f"[dim]Command:[/dim] {' '.join(cmd)}")
        if code == 127:
            console.print(f"[yellow]<{cmd[0]} not found — skipping>[/yellow]")
            return
        if raw_bytes:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            txt = stdout.decode('utf-8', errors='replace') if stdout else '<no output>'
            console.print(Panel(txt, title='stdout', style='white on black'))
            if stderr:
                console.print(Panel(stderr.decode('utf-8', errors='replace'), title='stderr', style='red'))
            return
        txt = out.rstrip() if out else '<no output>'
        panel_style = 'white'
        console.print(Panel(txt, title=title, style=panel_style))
        if err:
            console.print(Panel(err.rstrip(), title='stderr', style='red'))
    else:
        # fallback
        print(f"\n=== {title} ===")
        if show_cmd:
            print(f"Command: {' '.join(cmd)}\n")
        if code == 127:
            print(f"<{cmd[0]} not found — skipping>")
            return
        if raw_bytes:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if stdout:
                print(stdout.decode('utf-8', errors='replace'))
            else:
                print('<no output>')
            if stderr:
                print('\n<stderr>')
                print(stderr.decode('utf-8', errors='replace'))
            return
        if out is None or out.strip() == '':
            print('<no output>')
        else:
            print(out.rstrip())
        if err:
            print('\n<stderr>')
            print(err.rstrip())


def compare_case(title: str, ugrep_cmd, rg_cmd, *, special=None):
    print('\n' + '#' * 25)
    print(f"# {title}")
    print('#' * 25 + '\n')
    # use rich styles when available: ugrep green, rg cyan
    if has_cmd('ugrep'):
        if special == 'null_and_resolve':
            code, out, err = run_cmd(ugrep_cmd, capture_output=True, text=False)
            if code == 127:
                if Console is not None:
                    Console().print('[yellow]<ugrep not found — skipping>[/yellow]')
                else:
                    print('<ugrep not found — skipping>')
            else:
                parts = out.split(b'\0') if out else []
                if not parts:
                    if Console is not None:
                        Console().print('<no output>')
                    else:
                        print('<no output>')
                else:
                    for p in parts:
                        if not p:
                            continue
                        try:
                            rp = Path(p.decode('utf-8', errors='surrogateescape')).resolve()
                            if Console is not None:
                                Console().print(rp, style='green')
                            else:
                                print(rp)
                        except Exception as e:
                            print(f"<path error: {e}>")
        else:
            # ugrep block in green
            if Console is not None:
                print_block('ugrep', ugrep_cmd)
            else:
                print_block('ugrep', ugrep_cmd)
    else:
        if Console is not None:
            Console().print('[yellow]ugrep not found — skipping[/yellow]')
        else:
            print('ugrep not found — skipping')

    if has_cmd('rg'):
        if special == 'null_and_resolve':
            code, out, err = run_cmd(rg_cmd, capture_output=True, text=False)
            if code == 127:
                if Console is not None:
                    Console().print('[yellow]<rg not found — skipping>[/yellow]')
                else:
                    print('<rg not found — skipping>')
            else:
                parts = out.split(b'\0') if out else []
                if not parts:
                    if Console is not None:
                        Console().print('<no output>')
                    else:
                        print('<no output>')
                else:
                    for p in parts:
                        if not p:
                            continue
                        try:
                            rp = Path(p.decode('utf-8', errors='surrogateescape')).resolve()
                            if Console is not None:
                                Console().print(rp, style='cyan')
                            else:
                                print(rp)
                        except Exception as e:
                            print(f"<path error: {e}>")
        else:
            # rg block in cyan
            if Console is not None:
                print_block('rg (ripgrep)', rg_cmd)
            else:
                print_block('rg (ripgrep)', rg_cmd)
    else:
        if Console is not None:
            Console().print('[yellow]rg not found — skipping[/yellow]')
        else:
            print('rg not found — skipping')


def main():
    write_demo_files(DEMO)
    base = str(DEMO)

    # Each command is a list for subprocess
    compare_case(
        'Basic recursive, case-insensitive search for "avif"',
        ['ugrep', '-n', '-r', '-i', '--include=*.txt', '--include=*.log', 'avif', base],
        ['rg', '-n', '-i', '-g', '*.txt', '-g', '*.log', 'avif', base]
    )

    compare_case(
        'List files that contain the match (-l)',
        ['ugrep', '-l', '-r', '-i', '--include=*.txt', 'avif', base],
        ['rg', '-l', '-i', '-g', '*.txt', 'avif', base]
    )

    compare_case(
        'List files that do NOT contain the match (-L)',
        ['ugrep', '-L', '-r', '-i', '--include=*.txt', 'avif', base],
        ['rg', '-L', '-i', '-g', '*.txt', 'avif', base]
    )

    compare_case(
        'Count matches per file (-c)',
        ['ugrep', '-c', '-r', '--include=*.txt', 'avif', base],
        ['rg', '-c', '-g', '*.txt', 'avif', base]
    )

    compare_case(
        'Null-separated filenames (safe for spaces) and convert to absolute paths',
        ['ugrep', '-0', '-l', '-r', '--include=*.txt', 'avif', base],
        ['rg', '-0', '-l', '-g', '*.txt', 'avif', base],
        special='null_and_resolve'
    )

    compare_case(
        'PCRE (-P) example: alternation and word boundaries',
        ['ugrep', '-n', '-P', '-r', '--include=*.txt', r'\b(avif|AVIF)\b', base],
        ['rg', '-n', '-P', '-g', '*.txt', r'\b(avif|AVIF)\b', base]
    )

    compare_case(
        'Context lines (-C, -A, -B)',
        ['ugrep', '-n', '-C2', '-r', '--include=*.txt', 'Hello', base],
        ['rg', '-n', '-C2', '-g', '*.txt', 'Hello', base]
    )

    compare_case(
        'Treat binary as text (-a) and search binary content',
        ['ugrep', '-a', '-n', '-r', '255', base],
        ['rg', '-a', '-n', '255', base]
    )

    compare_case(
        'Include / Exclude patterns',
        ['ugrep', '-n', '-r', '--include=*.md', '--exclude=file2.log', 'Notes', base],
        ['rg', '-n', '-g', '*.md', '-g', '!file2.log', 'Notes', base]
    )

    compare_case(
        'Show formatted output (ugrep --format) vs rg color',
        ['ugrep', '-n', '--color=always', '--format=%n:%f:%l', '-r', '--include=*.txt', 'avif', base],
        ['rg', '--color=always', '-n', '-g', '*.txt', 'avif', base]
    )

    print('\nDemo finished. If a tool was missing, install it and re-run the script.')
    print('\nNotes:\n - This script demonstrates common flags and equivalent rg flags but is not exhaustive.\n - ugrep supports additional advanced formats and file-type magic; consult their manpages for full coverage.')


if __name__ == '__main__':
    main()
