"""Command-line interface for findz."""

import csv
import sys
from pathlib import Path
from typing import Iterator, Optional, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown

from .filter.filter import create_filter
from .filter.size import format_size
from .find.find import FIELDS, FileInfo
from .find.walk import WalkParams, walk


app = typer.Typer(
    name="findz",
    help="Search for files with SQL-like WHERE clause syntax",
    add_completion=False,
)
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


def show_filter_help():
    """Display filter syntax help."""
    help_text = """
# findz Filter Syntax

findz uses a filter syntax similar to SQL WHERE clauses.

## Examples

```bash
# Find files smaller than 10KB
findz 'size<10k'

# Find files in a size range
findz 'size between 1M and 1G' /some/path

# Find files modified before 2010 in archives
findz 'date<"2010" and archive="tar"'

# Find files named foo* modified today
findz 'name like "foo%" and date=today'

# Find files with regex
findz 'name rlike "(.*-){2}"'

# Find by extension
findz 'ext in ("jpg","jpeg")'

# Find directories
findz 'name in ("foo", "bar") and type="dir"'
```

## File Properties

- **name** - Name of the file
- **path** - Full path of the file
- **size** - File size (uncompressed)
- **date** - Modified date (YYYY-MM-DD)
- **time** - Modified time (HH:MM:SS)
- **ext** - Short extension (e.g. 'txt')
- **ext2** - Long extension (e.g. 'tar.gz')
- **type** - file|dir|link
- **archive** - Archive type (tar|zip|7z|rar)
- **container** - Path of container

## Helper Properties

- **today** - Today's date
- **mo, tu, we, th, fr, sa, su** - Last weekday dates

## Operators

- **Comparison**: =, !=, <>, <, >, <=, >=
- **Logical**: AND, OR, NOT
- **Pattern**: LIKE, ILIKE (case-insensitive), RLIKE (regex)
- **Range**: BETWEEN, IN
    """
    console.print(Markdown(help_text))


def interactive_mode():
    """Enter interactive mode for building queries."""
    console.print(Panel.fit(
        "[bold cyan]findz Interactive Mode[/bold cyan]\n"
        "Build your file search query step by step",
        border_style="cyan"
    ))
    
    # Ask for search path
    search_path = Prompt.ask(
        "[cyan]Search path[/cyan]",
        default="."
    )
    
    # Ask for filter type
    console.print("\n[bold]Choose a filter type:[/bold]")
    console.print("1. Size filter")
    console.print("2. Name filter")
    console.print("3. Date filter")
    console.print("4. Extension filter")
    console.print("5. Type filter")
    console.print("6. Archive filter")
    console.print("7. Custom filter (advanced)")
    
    choice = Prompt.ask("[cyan]Enter choice[/cyan]", choices=["1", "2", "3", "4", "5", "6", "7"])
    
    where_clause = ""
    
    if choice == "1":
        # Size filter
        op = Prompt.ask(
            "[cyan]Operator[/cyan]",
            choices=["<", ">", "<=", ">=", "=", "between"],
            default=">"
        )
        if op == "between":
            min_size = Prompt.ask("[cyan]Minimum size (e.g., 1M)[/cyan]")
            max_size = Prompt.ask("[cyan]Maximum size (e.g., 100M)[/cyan]")
            where_clause = f'size between {min_size} and {max_size}'
        else:
            size = Prompt.ask("[cyan]Size (e.g., 10M, 1G)[/cyan]")
            where_clause = f'size {op} {size}'
    
    elif choice == "2":
        # Name filter
        pattern_type = Prompt.ask(
            "[cyan]Pattern type[/cyan]",
            choices=["exact", "like", "ilike", "rlike"],
            default="like"
        )
        pattern = Prompt.ask("[cyan]Pattern (use % for wildcard)[/cyan]")
        
        if pattern_type == "exact":
            where_clause = f'name = "{pattern}"'
        else:
            where_clause = f'name {pattern_type} "{pattern}"'
    
    elif choice == "3":
        # Date filter
        date_type = Prompt.ask(
            "[cyan]Date type[/cyan]",
            choices=["today", "this week", "specific", "range"],
            default="today"
        )
        
        if date_type == "today":
            where_clause = 'date = today'
        elif date_type == "this week":
            where_clause = 'date >= mo'
        elif date_type == "specific":
            date = Prompt.ask("[cyan]Date (YYYY-MM-DD)[/cyan]")
            op = Prompt.ask("[cyan]Operator[/cyan]", choices=["=", ">", "<", ">=", "<="], default=">=")
            where_clause = f'date {op} "{date}"'
        else:
            start_date = Prompt.ask("[cyan]Start date (YYYY-MM-DD)[/cyan]")
            end_date = Prompt.ask("[cyan]End date (YYYY-MM-DD)[/cyan]")
            where_clause = f'date between "{start_date}" and "{end_date}"'
    
    elif choice == "4":
        # Extension filter
        exts = Prompt.ask("[cyan]Extensions (comma-separated, e.g., py,js,txt)[/cyan]")
        ext_list = [f'"{e.strip()}"' for e in exts.split(",")]
        if len(ext_list) == 1:
            where_clause = f'ext = {ext_list[0]}'
        else:
            where_clause = f'ext in ({", ".join(ext_list)})'
    
    elif choice == "5":
        # Type filter
        file_type = Prompt.ask(
            "[cyan]File type[/cyan]",
            choices=["file", "dir", "link"],
            default="file"
        )
        where_clause = f'type = "{file_type}"'
    
    elif choice == "6":
        # Archive filter
        archive_type = Prompt.ask(
            "[cyan]Archive type[/cyan]",
            choices=["any", "tar", "zip", "7z", "rar"],
            default="any"
        )
        if archive_type == "any":
            where_clause = 'archive <> ""'
        else:
            where_clause = f'archive = "{archive_type}"'
    
    else:
        # Custom filter
        where_clause = Prompt.ask("[cyan]Enter WHERE clause[/cyan]")
    
    # Ask for additional options
    console.print("\n[bold]Additional options:[/bold]")
    long_format = Confirm.ask("[cyan]Use long listing format?[/cyan]", default=False)
    csv_output = Confirm.ask("[cyan]Output as CSV?[/cyan]", default=False)
    follow_symlinks = Confirm.ask("[cyan]Follow symbolic links?[/cyan]", default=False)
    
    # Display the query
    console.print(Panel(
        f"[bold]Search Path:[/bold] {search_path}\n"
        f"[bold]Filter:[/bold] {where_clause}\n"
        f"[bold]Long format:[/bold] {long_format}\n"
        f"[bold]CSV output:[/bold] {csv_output}\n"
        f"[bold]Follow symlinks:[/bold] {follow_symlinks}",
        title="[bold cyan]Query Summary[/bold cyan]",
        border_style="cyan"
    ))
    
    if not Confirm.ask("\n[cyan]Execute this query?[/cyan]", default=True):
        console.print("[yellow]Query cancelled.[/yellow]")
        return
    
    # Execute the query
    execute_search(
        where=where_clause,
        paths=(search_path,),
        long=long_format,
        csv_output=csv_output,
        csv_no_head=False,
        archive_separator="//",
        follow_symlinks=follow_symlinks,
        no_archive=False,
        print_zero=False,
    )


def search_nested_archives(
    paths: tuple[str, ...],
    long: bool,
    save_output: Optional[str],
    ask_save: bool,
    continue_on_error: bool,
):
    """
    搜索包含嵌套压缩包的外层压缩包
    
    参数:
        paths: 搜索路径
        long: 是否显示详细信息
        save_output: 输出文件路径
        ask_save: 是否询问保存
        continue_on_error: 遇到错误是否继续
    """
    from .find.walk import is_archive
    import os
    from datetime import datetime
    
    # 创建匹配所有文件的过滤器
    filter_expr = create_filter("1")
    
    # 错误收集
    errors = []
    def error_handler(msg: str) -> None:
        if continue_on_error:
            errors.append(msg)
        else:
            console.print(f"[bold red]错误:[/bold red] {msg}")
            raise RuntimeError(msg)
    
    # 收集包含嵌套压缩包的外层压缩包
    nested_containers = set()
    results = []  # 用于保存结果
    
    with console.status("[bold cyan]搜索嵌套压缩包中...[/bold cyan]", spinner="dots"):
        for search_path in paths:
            params = WalkParams(
                filter_expr=filter_expr,
                follow_symlinks=False,
                no_archive=False,  # 必须扫描压缩包内部
                error_handler=error_handler,
            )
            
            try:
                for file_info in walk(search_path, params):
                    # 检查是否在压缩包内（archive 不为空）
                    if file_info.archive:
                        # 检查文件本身是否是压缩包
                        if is_archive(file_info.name):
                            nested_containers.add(file_info.archive)
            except Exception as e:
                if continue_on_error:
                    errors.append(f"{e}")
                else:
                    # error_handler 已经打印了错误,这里直接返回
                    return
    
    # 转换为列表并排序
    result_archives = sorted(nested_containers)
    
    # 显示结果数量
    console.print(f"\n[bold cyan]找到 {len(result_archives)} 个包含嵌套压缩包的外层压缩包[/bold cyan]\n")
    
    # 打印结果到控制台
    for archive_path in result_archives:
        if long and os.path.exists(archive_path):
            try:
                stat = os.stat(archive_path)
                size = format_size(stat.st_size)
                date_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                line = f"{date_str} {size:>10} {archive_path}"
            except Exception:
                line = archive_path
        else:
            line = archive_path
        
        console.print(line)
        results.append(line)
    
    # 打印错误
    if errors:
        console.print()
        for error in errors[:10]:
            console.print(f"[bold yellow]警告:[/bold yellow] {error}")
        if len(errors) > 10:
            console.print(f"[yellow]...还有 {len(errors) - 10} 个警告未显示[/yellow]")
    
    # 保存结果
    output_content = "\n".join(results) if results else ""
    _handle_save_output(output_content, save_output, ask_save)


def _handle_save_output(
    output_content: Union[str, set],
    save_output: Optional[str],
    ask_save: bool,
    is_csv: bool = False,
) -> None:
    """处理保存输出到文件
    
    Args:
        output_content: 要保存的内容（字符串或集合）
        save_output: 输出文件路径（如果提供）
        ask_save: 是否询问用户是否保存
        is_csv: 是否为CSV格式
    """
    # 如果是集合，转换为字符串
    if isinstance(output_content, set):
        output_content = "\n".join(sorted(output_content))
    
    # 如果没有内容，不保存
    if not output_content.strip():
        return
    
    file_path = save_output
    
    # 如果需要询问用户
    if ask_save and not file_path:
        from rich.prompt import Confirm, Prompt
        
        should_save = Confirm.ask("\n[bold cyan]是否保存结果到文件?[/bold cyan]")
        if should_save:
            default_ext = ".csv" if is_csv else ".txt"
            file_path = Prompt.ask(
                "[bold cyan]请输入文件名[/bold cyan]",
                default=f"findz_results{default_ext}"
            )
    
    # 如果有文件路径，保存
    if file_path:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            console.print(f"[bold green]✓[/bold green] 结果已保存到: {file_path}")
        except Exception as e:
            console.print(f"[bold red]保存文件错误:[/bold red] {e}")


def execute_search(
    where: str,
    paths: tuple[str, ...],
    long: bool,
    csv_output: bool,
    csv_no_head: bool,
    archive_separator: str,
    follow_symlinks: bool,
    no_archive: bool,
    print_zero: bool,
    save_output: Optional[str] = None,
    ask_save: bool = False,
    continue_on_error: bool = True,
):
    """执行文件搜索"""
    # Line separator
    line_sep = "\0" if print_zero else "\n"
    
    # Create filter
    try:
        filter_expr = create_filter(where)
    except Exception as e:
        console.print(f"[bold red]解析过滤器错误:[/bold red] {e}")
        return
    
    # Error collection
    errors = []
    
    def error_handler(msg: str) -> None:
        if continue_on_error:
            errors.append(msg)
        else:
            console.print(f"[bold red]错误:[/bold red] {msg}")
            raise RuntimeError(msg)
    
    # Walk and collect results
    all_results = []
    output_lines = []  # 用于保存输出
    
    with console.status("[bold cyan]搜索文件中...[/bold cyan]", spinner="dots"):
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
                if continue_on_error:
                    errors.append(f"{e}")
                else:
                    # error_handler 已经打印了错误,这里直接返回
                    return
    
    # Display results count
    if not (csv_output or csv_no_head):
        console.print(f"\n[bold cyan]找到 {len(all_results)} 个文件[/bold cyan]\n")
    
    # Print results and collect output
    import io
    output_buffer = io.StringIO()
    
    if csv_output:
        print_csv(iter(all_results), header=True)
        # 重新生成用于保存
        writer = csv.writer(output_buffer)
        writer.writerow(FIELDS)
        for file in all_results:
            getter = file.context()
            row = [str(getter(field)) if getter(field) else "" for field in FIELDS]
            writer.writerow(row)
    elif csv_no_head:
        print_csv(iter(all_results), header=False)
        # 重新生成用于保存
        writer = csv.writer(output_buffer)
        for file in all_results:
            getter = file.context()
            row = [str(getter(field)) if getter(field) else "" for field in FIELDS]
            writer.writerow(row)
    else:
        for file in all_results:
            name = ""
            if file.container:
                name = file.container + archive_separator
            name += file.path
            
            if long:
                size = format_size(file.size)
                date_str = file.mod_time.strftime("%Y-%m-%d %H:%M:%S")
                line = f"{date_str} {size:>10} {name}"
            else:
                line = name
            
            # 使用 console.print 来正确处理所有字符
            if print_zero:
                console.print(line, end="\0")
            else:
                console.print(line)
            
            output_lines.append(line)
    
    # Handle save output
    if csv_output or csv_no_head:
        output_content = output_buffer.getvalue()
    else:
        output_content = line_sep.join(output_lines)
    
    _handle_save_output(output_content, save_output, ask_save, csv_output or csv_no_head)
    
    # Print errors
    if errors:
        console.print()
        console.print(f"[bold yellow]警告: 遇到 {len(errors)} 个错误[/bold yellow]")
        if len(errors) <= 10:
            for error in errors:
                console.print(f"[yellow]  - {error}[/yellow]")
        else:
            for error in errors[:10]:
                console.print(f"[yellow]  - {error}[/yellow]")
            console.print(f"[yellow]  ... 以及 {len(errors) - 10} 个其他错误[/yellow]")


@app.command()
def main(
    where: Optional[str] = typer.Argument(
        None,
        help="SQL WHERE-like filter expression. Use '-' to match all files."
    ),
    paths: Optional[list[str]] = typer.Argument(
        None,
        help="Paths to search (default: current directory)"
    ),
    filter_help: bool = typer.Option(
        False,
        "-H",
        "--filter-help",
        help="Show WHERE filter syntax help"
    ),
    long: bool = typer.Option(
        False,
        "-l",
        "--long",
        help="Show long listing format with date and size"
    ),
    csv_output: bool = typer.Option(
        False,
        "--csv",
        help="Output results as CSV with header"
    ),
    csv_no_head: bool = typer.Option(
        False,
        "--csv-no-head",
        help="Output results as CSV without header"
    ),
    archive_separator: str = typer.Option(
        "//",
        "--archive-separator",
        help="Separator between archive name and file inside"
    ),
    follow_symlinks: bool = typer.Option(
        False,
        "-L",
        "--follow-symlinks",
        help="Follow symbolic links"
    ),
    no_archive: bool = typer.Option(
        False,
        "-n",
        "--no-archive",
        help="禁用压缩包支持（加速大型文件树搜索）"
    ),
    nested: bool = typer.Option(
        False,
        "-N",
        "--nested",
        help="查找包含嵌套压缩包的外层压缩包（只输出外层压缩包路径）"
    ),
    save_output: Optional[str] = typer.Option(
        None,
        "-o",
        "--output",
        help="将结果保存到指定文件"
    ),
    ask_save: bool = typer.Option(
        False,
        "--ask-save",
        help="搜索结束后询问是否保存结果"
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="遇到错误时继续搜索（默认启用）"
    ),
    print_zero: bool = typer.Option(
        False,
        "-0",
        "--print0",
        help="使用空字符而非换行符分隔（配合 xargs -0）"
    ),
    version: bool = typer.Option(
        False,
        "-V",
        "--version",
        help="Show version information"
    ),
    interactive: bool = typer.Option(
        False,
        "-i",
        "--interactive",
        help="Enter interactive mode"
    ),
) -> None:
    """
    Search for files using SQL-like WHERE clause syntax.
    
    findz allows you to search for files, including inside archives,
    using familiar SQL WHERE syntax.
    
    Examples:
    
        findz 'size > 10M'
        
        findz 'ext = "py" and date = today'
        
        findz 'name like "test%" and size < 1K'
    """
    
    # Show filter help
    if filter_help:
        show_filter_help()
        return
    
    # Show version
    if version:
        from . import __version__
        console.print(f"[bold cyan]findz[/bold cyan] version {__version__}")
        console.print("A Python port of zfind - search files with SQL-like syntax")
        return
    
    # Enter interactive mode if requested or no arguments provided
    if interactive:
        interactive_mode()
        return
    
    # If no WHERE and no paths, enter interactive mode
    if where is None and not paths:
        interactive_mode()
        return
    
    # Handle nested mode (special case)
    # When in nested mode, the first argument (where) is actually the path
    if nested:
        # 在嵌套模式下,如果提供了 where,它实际上是路径
        if where and not paths:
            search_paths = (where,)
        elif paths:
            search_paths = tuple(paths)
        else:
            search_paths = (".",)
        
        search_nested_archives(
            paths=search_paths,
            long=long,
            save_output=save_output,
            ask_save=ask_save,
            continue_on_error=continue_on_error,
        )
        return
    
    # Handle WHERE parameter
    if not where or where == "-":
        where = "1"  # Match everything
    
    # Handle paths
    if not paths:
        paths = ["."]
    
    # Execute search
    execute_search(
        where=where,
        paths=tuple(paths),
        long=long,
        csv_output=csv_output,
        csv_no_head=csv_no_head,
        archive_separator=archive_separator,
        follow_symlinks=follow_symlinks,
        no_archive=no_archive,
        print_zero=print_zero,
        save_output=save_output,
        ask_save=ask_save,
        continue_on_error=continue_on_error,
    )


if __name__ == "__main__":
    app()



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


if __name__ == "__main__":
    app()

