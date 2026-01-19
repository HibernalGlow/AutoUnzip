"""CLI for mvz - Archive file manipulation tool."""

import os
import sys
from pathlib import Path
from typing import List, Optional, Iterable, Iterator

try:
    import pyperclip
except ImportError:
    pyperclip = None

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from .executor import batch_rename, delete_files, extract_files, find_7z
from .parser import group_by_archive, parse_input

app = typer.Typer(
    name="mvz",
    help="Manipulate files inside archives (input from findz)",
    add_completion=False,
)
console = Console()


def check_7z():
    """Check if 7z is available."""
    if not find_7z():
        console.print("[bold red]Error:[/bold red] 7-Zip (7z) not found in PATH or common locations.")
        console.print("Please install 7-Zip to use this tool.")
        raise typer.Exit(1)


def get_input_iterator(
    input_file: Optional[Path] = None,
    clipboard: bool = False,
) -> Iterator[str]:
    """Get iterator for input lines from file, clipboard, or stdin."""
    if input_file:
        if not input_file.exists():
            console.print(f"[red]Error: Input file not found: {input_file}[/red]")
            raise typer.Exit(1)
        # We read the whole file to avoid keeping it open or potential issues with yielding from closed file
        # For huge files this might be an issue but for this tool's purpose it's fine.
        # Actually, yielding from context manager works if we consume it immediately.
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                yield line
        return

    if clipboard:
        if pyperclip is None:
            console.print("[red]Error: pyperclip not installed. Cannot read from clipboard.[/red]")
            console.print("Install with: pip install pyperclip")
            raise typer.Exit(1)
        
        content = pyperclip.paste()
        if not content:
            console.print("[yellow]Clipboard is empty.[/yellow]")
            return
            
        for line in content.splitlines():
            yield line
        return
    
    # Default to stdin
    if sys.stdin.isatty():
        console.print("[yellow]Waiting for input from stdin (e.g., findz ... | mvz ...)[/yellow]")
        console.print("[dim]Or use --input/-i <file> or --clipboard/--clip[/dim]")
        
    for line in sys.stdin:
        yield line


@app.command()
def delete(
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input file containing paths"),
    clipboard: bool = typer.Option(False, "--clipboard", "--clip", help="Read input from clipboard"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without executing"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Delete files from archives."""
    check_7z()
    
    iterator = get_input_iterator(input_file, clipboard)
    entries = list(parse_input(iterator, separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    table = Table(title="Files to Delete")
    table.add_column("Archive", style="cyan")
    table.add_column("Internal Path", style="magenta")
    
    for archive_path, archive_entries in groups.items():
        for entry in archive_entries:
            table.add_row(Path(archive_path).name, entry.internal_path)
    
    console.print(table)
    
    if dry_run:
        console.print("[bold yellow]Dry run mode: No files will be deleted.[/bold yellow]")
        return
        
    if confirm and not Confirm.ask(f"Are you sure you want to delete {len(entries)} file(s) from archives?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return
        
    for archive_path, archive_entries in groups.items():
        internal_paths = [e.internal_path for e in archive_entries]
        result = delete_files(archive_path, internal_paths, dry_run=False)
        if result.success:
            console.print(f"[green]✓[/green] {result.message}")
        else:
            console.print(f"[red]✗[/red] {result.message}")


@app.command()
def extract(
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input file containing paths"),
    clipboard: bool = typer.Option(False, "--clipboard", "--clip", help="Read input from clipboard"),
    output: str = typer.Option(".", "-o", "--output", help="Base output directory"),
    near: bool = typer.Option(False, "--near", help="Extract near the source archive"),
    auto_dir: bool = typer.Option(False, "--auto-dir", help="Create subfolder named after archive"),
    flatten: bool = typer.Option(False, "--flatten", help="Extract without internal directory structure"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Extract files from archives."""
    check_7z()
    
    iterator = get_input_iterator(input_file, clipboard)
    entries = list(parse_input(iterator, separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    for archive_path, archive_entries in groups.items():
        internal_paths = [e.internal_path for e in archive_entries]
        
        # Calculate destination
        final_output = output
        if near:
            final_output = str(Path(archive_path).parent)
        
        if auto_dir:
            # Add archive stem as subfolder
            final_output = str(Path(final_output) / Path(archive_path).stem)
            
        result = extract_files(archive_path, internal_paths, final_output, dry_run=dry_run, flatten=flatten)
        if result.success:
            console.print(f"[green]✓[/green] {result.message}")
        else:
            console.print(f"[red]✗[/red] {result.message}")


@app.command()
def move(
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input file containing paths"),
    clipboard: bool = typer.Option(False, "--clipboard", "--clip", help="Read input from clipboard"),
    output: str = typer.Option(".", "-o", "--output", help="Base destination directory"),
    near: bool = typer.Option(False, "--near", help="Extract near the source archive"),
    auto_dir: bool = typer.Option(False, "--auto-dir", help="Create subfolder named after archive"),
    flatten: bool = typer.Option(False, "--flatten", help="Extract without internal directory structure"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Move files OUT of archives to a directory (extract + delete)."""
    check_7z()
    
    iterator = get_input_iterator(input_file, clipboard)
    entries = list(parse_input(iterator, separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    console.print(f"Plan: Move {len(entries)} file(s) from archives.")
    
    if confirm and not dry_run and not Confirm.ask("Proceed with move operation (extraction followed by deletion)?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    for archive_path, archive_entries in groups.items():
        internal_paths = [e.internal_path for e in archive_entries]
        
        # Calculate destination
        final_output = output
        if near:
            final_output = str(Path(archive_path).parent)
        
        if auto_dir:
            final_output = str(Path(final_output) / Path(archive_path).stem)
            
        # 1. Extract
        ext_result = extract_files(archive_path, internal_paths, final_output, dry_run=dry_run, flatten=flatten)
        if not ext_result.success:
            console.print(f"[red]✗ Extraction failed for {archive_path}, skipping deletion.[/red]")
            console.print(f"  Error: {ext_result.message}")
            continue
            
        if dry_run:
            console.print(f"[yellow]i[/yellow] {ext_result.message}")
        else:
            console.print(f"[green]✓[/green] Extracted files to {final_output}")
        
        # 2. Delete from archive
        del_result = delete_files(archive_path, internal_paths, dry_run=dry_run)
        if del_result.success:
            if dry_run:
                console.print(f"[yellow]i[/yellow] {del_result.message}")
            else:
                console.print(f"[green]✓[/green] Removed original files from {Path(archive_path).name}")
        else:
            console.print(f"[red]✗ Failed to remove originals from {archive_path}[/red]")
            console.print(f"  Error: {del_result.message}")


@app.command()
def rename(
    pattern: str = typer.Argument(..., help="Regex pattern to find"),
    replacement: str = typer.Argument(..., help="Replacement string"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input file containing paths"),
    clipboard: bool = typer.Option(False, "--clipboard", "--clip", help="Read input from clipboard"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
):
    """Rename files inside archives using regex."""
    import re
    check_7z()
    
    iterator = get_input_iterator(input_file, clipboard)
    entries = list(parse_input(iterator, separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    all_rename_pairs = []
    
    for archive_path, archive_entries in groups.items():
        pairs = []
        for entry in archive_entries:
            new_name = re.sub(pattern, replacement, entry.internal_path)
            if new_name != entry.internal_path:
                pairs.append((entry.internal_path, new_name))
        
        if pairs:
            all_rename_pairs.append((archive_path, pairs))

    if not all_rename_pairs:
        console.print("[yellow]No files matched the rename pattern.[/yellow]")
        return

    table = Table(title="Internal Renames")
    table.add_column("Archive", style="cyan")
    table.add_column("Old Path", style="red")
    table.add_column("New Path", style="green")
    
    for archive_path, pairs in all_rename_pairs:
        for old, new in pairs:
            table.add_row(Path(archive_path).name, old, new)
            
    console.print(table)
    
    if dry_run:
        console.print("[bold yellow]Dry run mode: No renames will be executed.[/bold yellow]")
        return
        
    if confirm and not Confirm.ask("Proceed with renaming?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    for archive_path, pairs in all_rename_pairs:
        result = batch_rename(archive_path, pairs, dry_run=False)
        if result.success:
            console.print(f"[green]✓[/green] {result.message}")
        else:
            console.print(f"[red]✗[/red] {result.message}")


def main():
    """Entry point for the mvz CLI."""
    app()


if __name__ == "__main__":
    main()
