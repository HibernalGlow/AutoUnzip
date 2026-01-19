"""CLI for mvz - Archive file manipulation tool."""

import os
import sys
from pathlib import Path
from typing import List, Optional

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


@app.command()
def delete(
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without executing"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Delete files from archives (read from stdin)."""
    check_7z()
    
    if sys.stdin.isatty():
        console.print("[yellow]Waiting for input from stdin (e.g., findz ... | mvz delete)[/yellow]")
    
    entries = list(parse_input(separator=separator))
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
    output: str = typer.Option(".", "-o", "--output", help="Output directory"),
    flatten: bool = typer.Option(False, "--flatten", help="Extract without internal directory structure"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Extract files from archives (read from stdin)."""
    check_7z()
    
    entries = list(parse_input(separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    for archive_path, archive_entries in groups.items():
        internal_paths = [e.internal_path for e in archive_entries]
        result = extract_files(archive_path, internal_paths, output, dry_run=dry_run, flatten=flatten)
        if result.success:
            console.print(f"[green]✓[/green] {result.message}")
        else:
            console.print(f"[red]✗[/red] {result.message}")


@app.command()
def move(
    output: str = typer.Option(".", "-o", "--output", help="Destination directory outside"),
    flatten: bool = typer.Option(False, "--flatten", help="Extract without internal directory structure"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
):
    """Move files OUT of archives to a directory (extract + delete)."""
    check_7z()
    
    entries = list(parse_input(separator=separator))
    if not entries:
        console.print("[yellow]No archive entries found in input.[/yellow]")
        return

    groups = group_by_archive(entries)
    
    console.print(f"Plan: Move {len(entries)} file(s) from archives to [cyan]{output}[/cyan]")
    
    if dry_run:
        console.print("[bold yellow]Dry run mode: No operations will be executed.[/bold yellow]")
        for archive_path, archive_entries in groups.items():
            internal_paths = [e.internal_path for e in archive_entries]
            console.print(f"  [cyan]{Path(archive_path).name}[/cyan] -> {len(internal_paths)} files")
        return
        
    if confirm and not Confirm.ask("Proceed with move operation (extraction followed by deletion)?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    for archive_path, archive_entries in groups.items():
        internal_paths = [e.internal_path for e in archive_entries]
        
        ext_result = extract_files(archive_path, internal_paths, output, dry_run=False, flatten=flatten)
        if not ext_result.success:
            console.print(f"[red]✗ Extraction failed for {archive_path}, skipping deletion.[/red]")
            console.print(f"  Error: {ext_result.message}")
            continue
            
        console.print(f"[green]✓[/green] Extracted files from {Path(archive_path).name}")
        
        del_result = delete_files(archive_path, internal_paths, dry_run=False)
        if del_result.success:
            console.print(f"[green]✓[/green] Removed original files from {Path(archive_path).name}")
        else:
            console.print(f"[red]✗ Failed to remove originals from {archive_path}[/red]")
            console.print(f"  Error: {del_result.message}")


@app.command()
def rename(
    pattern: str = typer.Argument(..., help="Regex pattern to find"),
    replacement: str = typer.Argument(..., help="Replacement string"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    separator: str = typer.Option("//", "--sep", help="Separator between archive and internal path"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Ask for confirmation"),
):
    """Rename files inside archives using regex (read from stdin)."""
    import re
    check_7z()
    
    entries = list(parse_input(separator=separator))
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
