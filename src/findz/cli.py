"""Command-line interface for findz."""

import csv
import sys
from pathlib import Path
from typing import Iterator, Optional

import click
from rich.console import Console

from .filter.filter import create_filter
from .filter.size import format_size
from .find.find import FIELDS, FileInfo
from .find.walk import WalkParams, walk


console = Console()


def print_files(
    files: Iterator[FileInfo],
    long: bool = False,
    archive_sep: str = "//",
    line_sep: str = "\n",
) -> None:
    """Print files in plain text format.
    
    Args:
        files: Iterator of FileInfo objects
        long: Whether to use long listing format
        archive_sep: Separator between archive and file path
        line_sep: Line separator character(s)
    """
    for file in files:
        name = ""
        if file.container:
            name = file.container + archive_sep
        name += file.path
        
        if long:
            size = format_size(file.size)
            date_str = file.mod_time.strftime("%Y-%m-%d %H:%M:%S")
            sys.stdout.write(f"{date_str} {size:>10} {name}")
        else:
            sys.stdout.write(name)
        
        sys.stdout.write(line_sep)
        sys.stdout.flush()


def print_csv(
    files: Iterator[FileInfo],
    header: bool = True,
) -> None:
    """Print files in CSV format.
    
    Args:
        files: Iterator of FileInfo objects
        header: Whether to print CSV header
    """
    writer = csv.writer(sys.stdout)
    
    if header:
        writer.writerow(FIELDS)
    
    for file in files:
        getter = file.context()
        row = []
        for field in FIELDS:
            value = getter(field)
            row.append(str(value) if value else "")
        writer.writerow(row)


@click.command()
@click.argument("where", required=False, default="")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "-H",
    "--filter-help",
    is_flag=True,
    help="Show where-filter help.",
)
@click.option(
    "-l",
    "--long",
    is_flag=True,
    help="Show long listing format.",
)
@click.option(
    "--csv",
    "csv_output",
    is_flag=True,
    help="Show listing as CSV.",
)
@click.option(
    "--csv-no-head",
    is_flag=True,
    help="Show listing as CSV without header.",
)
@click.option(
    "--archive-separator",
    default="//",
    help="Separator between archive name and file inside.",
)
@click.option(
    "-L",
    "--follow-symlinks",
    is_flag=True,
    help="Follow symbolic links.",
)
@click.option(
    "-n",
    "--no-archive",
    is_flag=True,
    help="Disables archive support.",
)
@click.option(
    "-0",
    "--print0",
    "print_zero",
    is_flag=True,
    help="Use null character instead of newline.",
)
@click.option(
    "-V",
    "--version",
    is_flag=True,
    help="Show version.",
)
def main(
    where: str,
    paths: tuple[str, ...],
    filter_help: bool,
    long: bool,
    csv_output: bool,
    csv_no_head: bool,
    archive_separator: str,
    follow_symlinks: bool,
    no_archive: bool,
    print_zero: bool,
    version: bool,
) -> None:
    """Search for files with SQL-like WHERE clause.
    
    WHERE: The filter using SQL-where syntax (use '-' to skip when providing paths)
    PATHS: Paths to search (default: current directory)
    """
    
    if filter_help:
        console.print(FILTER_HELP)
        sys.exit(0)
    
    if version:
        from . import __version__
        console.print(f"findz {__version__}")
        sys.exit(0)
    
    # Handle WHERE parameter
    if not where or where == "-":
        where = "1"  # Match everything
    
    # Handle paths
    if not paths:
        paths = (".",)
    
    # Line separator
    line_sep = "\0" if print_zero else "\n"
    
    # Create filter
    try:
        filter_expr = create_filter(where)
    except Exception as e:
        console.print(f"[red]Error parsing filter:[/red] {e}", style="bold red")
        sys.exit(1)
    
    # Error collection
    errors = []
    
    def error_handler(msg: str) -> None:
        errors.append(msg)
    
    # Walk and collect results
    all_results = []
    
    for search_path in paths:
        params = WalkParams(
            filter_expr=filter_expr,
            follow_symlinks=follow_symlinks,
            no_archive=no_archive,
            error_handler=error_handler,
        )
        
        try:
            for file_info in walk(search_path, params):
                all_results.append(file_info)
        except Exception as e:
            console.print(f"[red]Error walking {search_path}:[/red] {e}", style="bold red")
    
    # Print results
    if csv_output:
        print_csv(iter(all_results), header=True)
    elif csv_no_head:
        print_csv(iter(all_results), header=False)
    else:
        print_files(iter(all_results), long=long, archive_sep=archive_separator, line_sep=line_sep)
    
    # Print errors
    if errors:
        for error in errors:
            console.print(f"[red]error:[/red] {error}", style="bold red", err=True)
        console.print("[red]errors were encountered![/red]", style="bold red", err=True)
        sys.exit(1)


FILTER_HELP = """
[bold cyan]findz[/bold cyan] uses a filter syntax that is very similar to an SQL-WHERE clause.

[bold]Examples:[/bold]

  # find files smaller than 10KB, in the current path
  findz 'size<10k'

  # find files in the given range in /some/path
  findz 'size between 1M and 1G' /some/path

  # find files modified before 2010 inside a tar
  findz 'date<"2010" and archive="tar"'

  # find files named foo* and modified today
  findz 'name like "foo%" and date=today'

  # find files that contain two dashes using a regex
  findz 'name rlike "(.*-){2}"'

  # find files that have the extension .jpg or .jpeg
  findz 'ext in ("jpg","jpeg")'

  # find directories named foo and bar
  findz 'name in ("foo", "bar") and type="dir"'

  # search for all README.md files and show in long listing format
  findz 'name="README.md"' -l

  # show results in csv format
  findz --csv
  findz --csv-no-head

[bold]The following file properties are available:[/bold]

  [cyan]name[/cyan]        name of the file
  [cyan]path[/cyan]        full path of the file
  [cyan]size[/cyan]        file size (uncompressed)
  [cyan]date[/cyan]        modified date in YYYY-MM-DD format
  [cyan]time[/cyan]        modified time in HH-MM-SS format
  [cyan]ext[/cyan]         short file extension (e.g. 'txt')
  [cyan]ext2[/cyan]        long file extension (two parts, e.g. 'tar.gz')
  [cyan]type[/cyan]        file|dir|link
  [cyan]archive[/cyan]     archive type tar|zip|7z|rar if inside a container
  [cyan]container[/cyan]   path of container (if any)

[bold]Helper properties:[/bold]

  [cyan]today[/cyan]       today's date
  [cyan]mo[/cyan]          last Monday's date
  [cyan]tu[/cyan]          last Tuesday's date
  [cyan]we[/cyan]          last Wednesday's date
  [cyan]th[/cyan]          last Thursday's date
  [cyan]fr[/cyan]          last Friday's date
  [cyan]sa[/cyan]          last Saturday's date
  [cyan]su[/cyan]          last Sunday's date

For more details go to https://github.com/laktak/zfind
"""


if __name__ == "__main__":
    main()
