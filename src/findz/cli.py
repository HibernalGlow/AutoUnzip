"""Command-line interface for findz."""

import csv
import json
import os
import re
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Union, List, Dict, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown

from .filter.filter import create_filter
from .filter.size import format_size, parse_size
from .find.find import FIELDS, FileInfo
from .find.walk import WalkParams, walk


app = typer.Typer(
    name="findz",
    help="Search for files with SQL-like WHERE clause syntax",
    add_completion=False,
)
console = Console()

# 缓存目录和文件
CACHE_DIR = Path.home() / ".findz_cache"
LAST_RESULT_FILE = CACHE_DIR / "last_result.json"


def get_cache_dir() -> Path:
    """获取缓存目录，不存在则创建"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def file_info_to_dict(file_info: FileInfo) -> Dict[str, Any]:
    """将 FileInfo 转换为字典"""
    return {
        'name': file_info.name,
        'path': file_info.path,
        'size': file_info.size,
        'size_formatted': format_size(file_info.size),
        'mod_time': file_info.mod_time.isoformat(),
        'date': file_info.mod_time.strftime("%Y-%m-%d"),
        'time': file_info.mod_time.strftime("%H:%M:%S"),
        'type': file_info.file_type,
        'container': file_info.container or '',
        'archive': file_info.archive or '',
        'ext': os.path.splitext(file_info.name)[1].lstrip('.').lower(),
    }


def save_results_cache(results: List[Dict[str, Any]], metadata: Dict[str, Any] = None) -> None:
    """保存搜索结果到缓存文件"""
    get_cache_dir()
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'metadata': metadata or {},
        'count': len(results),
        'files': results,
    }
    with open(LAST_RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def load_results_cache() -> Optional[Dict[str, Any]]:
    """加载缓存的搜索结果"""
    if not LAST_RESULT_FILE.exists():
        return None
    try:
        with open(LAST_RESULT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def parse_refine_filter(filter_str: str) -> Dict[str, Any]:
    """
    解析二次筛选表达式
    
    支持的格式:
    - count > 10
    - avg_size > 1M
    - total_size < 100M
    - ext = jpg
    - name like test%
    """
    filter_str = filter_str.strip()
    result = {}
    
    # 解析多个条件（用 AND 分隔）
    conditions = re.split(r'\s+AND\s+', filter_str, flags=re.IGNORECASE)
    
    for cond in conditions:
        cond = cond.strip()
        
        # 匹配: field op value
        match = re.match(r'(\w+)\s*(>=|<=|!=|<>|>|<|=|LIKE|RLIKE)\s*(.+)', cond, re.IGNORECASE)
        if match:
            field, op, value = match.groups()
            field = field.lower()
            op = op.upper()
            value = value.strip().strip('"\'')
            
            # 解析大小值
            if field in ('avg_size', 'total_size', 'size'):
                try:
                    value = parse_size(value)
                except:
                    pass
            elif field == 'count':
                try:
                    value = int(value)
                except:
                    pass
            
            result[field] = {'op': op, 'value': value}
    
    return result


def apply_refine_filter(groups: List[Dict], filter_dict: Dict[str, Any]) -> List[Dict]:
    """应用二次筛选条件到分组结果"""
    def match_condition(item: Dict, field: str, op: str, value: Any) -> bool:
        item_value = item.get(field)
        if item_value is None:
            return False
        
        if op == '=':
            return str(item_value).lower() == str(value).lower()
        elif op in ('!=', '<>'):
            return str(item_value).lower() != str(value).lower()
        elif op == '>':
            return item_value > value
        elif op == '<':
            return item_value < value
        elif op == '>=':
            return item_value >= value
        elif op == '<=':
            return item_value <= value
        elif op == 'LIKE':
            pattern = value.replace('%', '.*').replace('_', '.')
            return bool(re.match(pattern, str(item_value), re.IGNORECASE))
        elif op == 'RLIKE':
            return bool(re.search(value, str(item_value), re.IGNORECASE))
        return True
    
    filtered = []
    for group in groups:
        match = True
        for field, cond in filter_dict.items():
            if not match_condition(group, field, cond['op'], cond['value']):
                match = False
                break
        if match:
            filtered.append(group)
    
    return filtered


def group_files(files: List[Dict], group_by: str) -> List[Dict]:
    """
    按指定字段分组文件
    
    Args:
        files: 文件列表
        group_by: 分组字段 (archive/ext/dir)
    
    Returns:
        分组统计列表
    """
    groups: Dict[str, Dict] = {}
    
    for f in files:
        # 确定分组键
        if group_by == 'archive':
            key = f.get('archive') or f.get('container') or ''
            if not key:
                continue  # 跳过不在压缩包内的文件
        elif group_by == 'ext':
            key = f.get('ext', '') or '(无扩展名)'
        elif group_by == 'dir':
            full_path = f.get('container', '')
            if full_path:
                full_path += '//' + f.get('path', '')
            else:
                full_path = f.get('path', '')
            parts = re.split(r'[/\\]|//', full_path)
            key = '/'.join(parts[:-1]) if len(parts) > 1 else '(根目录)'
        else:
            key = str(f.get(group_by, ''))
        
        if key not in groups:
            groups[key] = {
                'key': key,
                'name': key.split('/')[-1] if '/' in key else key,
                'count': 0,
                'total_size': 0,
                'files': [],
            }
        
        groups[key]['count'] += 1
        groups[key]['total_size'] += f.get('size', 0)
        groups[key]['files'].append(f)
    
    # 计算平均大小
    result = []
    for g in groups.values():
        g['avg_size'] = g['total_size'] / g['count'] if g['count'] > 0 else 0
        g['avg_size_formatted'] = format_size(g['avg_size'])
        g['total_size_formatted'] = format_size(g['total_size'])
        result.append(g)
    
    return result


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
    json_output: bool,
    archive_separator: str,
    follow_symlinks: bool,
    no_archive: bool,
    archives_only: bool,
    print_zero: bool,
    save_output: Optional[str] = None,
    ask_save: bool = False,
    continue_on_error: bool = True,
    no_cache: bool = False,
    silent: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """执行文件搜索
    
    Returns:
        搜索结果列表（字典格式），用于后续分组处理
    """
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
    all_results_dict = []  # 用于 JSON 输出和缓存
    output_lines = []  # 用于保存输出
    
    # 静默模式不显示进度
    status_ctx = console.status("[bold cyan]搜索文件中...[/bold cyan]", spinner="dots") if not silent else nullcontext()
    
    with status_ctx:
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
                    all_results_dict.append(file_info_to_dict(file_info))
            except Exception as e:
                if continue_on_error:
                    errors.append(f"{e}")
                else:
                    # error_handler 已经打印了错误,这里直接返回
                    return

    # 保存结果到缓存（除非禁用）
    if not no_cache:
        save_results_cache(all_results_dict, {
            'where': where,
            'paths': list(paths),
            'archives_only': archives_only,
        })

    # If user requested archives-only, extract unique archive paths and print/save them
    if archives_only:
        # collect archive paths from results (non-empty)
        archives = [f.archive for f in all_results if getattr(f, "archive", None)]
        # preserve order and deduplicate
        unique_archives = list(dict.fromkeys(archives))

        # 静默模式：只返回结果，不输出
        if silent:
            # 构建压缩包信息列表返回
            archive_list = []
            for arch in unique_archives:
                item = {'path': arch, 'archive': arch, 'container': arch}
                if arch and Path(arch).exists():
                    try:
                        st = Path(arch).stat()
                        item['size'] = st.st_size
                        item['size_formatted'] = format_size(st.st_size)
                        item['name'] = Path(arch).name
                        item['ext'] = Path(arch).suffix.lstrip('.').lower()
                    except Exception:
                        pass
                archive_list.append(item)
            return archive_list

        # Display count
        if not json_output:
            console.print(f"\n[bold cyan]找到 {len(unique_archives)} 个压缩包[/bold cyan]\n")

        # JSON 输出
        if json_output:
            archive_list = []
            for arch in unique_archives:
                item = {'path': arch}
                if arch and Path(arch).exists():
                    try:
                        st = Path(arch).stat()
                        item['size'] = st.st_size
                        item['size_formatted'] = format_size(st.st_size)
                        item['mod_time'] = datetime.fromtimestamp(st.st_mtime).isoformat()
                    except Exception:
                        pass
                archive_list.append(item)
            
            output_content = json.dumps(archive_list, ensure_ascii=False, indent=2)
            console.print(output_content)
            _handle_save_output(output_content, save_output, ask_save, False)
            return all_results_dict

        # Prepare output lines
        out_lines: list[str] = []
        for arch in unique_archives:
            if long and arch and Path(arch).exists():
                try:
                    st = Path(arch).stat()
                    size = format_size(st.st_size)
                    date_str = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    line = f"{date_str} {size:>10} {arch}"
                except Exception:
                    line = arch
            else:
                line = arch
            console.print(line)
            out_lines.append(line)

        # Handle save
        output_content = "\n".join(out_lines)
        _handle_save_output(output_content, save_output, ask_save, False)

        # finished
        return all_results_dict

    # 静默模式：只返回结果
    if silent:
        return all_results_dict

    # JSON 输出
    if json_output:
        output_content = json.dumps(all_results_dict, ensure_ascii=False, indent=2)
        console.print(output_content)
        _handle_save_output(output_content, save_output, ask_save, False)
        return all_results_dict

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
    
    return all_results_dict


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
    json_output: bool = typer.Option(
        False,
        "--json",
        help="输出 JSON 格式（方便 jq 处理）"
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
    archives_only: bool = typer.Option(
        False,
        "-A",
        "--archives-only",
        help="只输出压缩包本身，不搜索内部"
    ),
    nested: bool = typer.Option(
        False,
        "-N",
        "--nested",
        help="查找包含嵌套压缩包的外层压缩包（只输出外层压缩包路径）"
    ),
    refine: Optional[str] = typer.Option(
        None,
        "-R",
        "--refine",
        help="二次筛选表达式，如 'avg_size > 1M' 或 'count > 10'（配合 -G 使用）"
    ),
    group_by: Optional[str] = typer.Option(
        None,
        "-G",
        "--group-by",
        help="分组统计: archive(压缩包)/ext(扩展名)/dir(目录)"
    ),
    sort_by: str = typer.Option(
        "avg_size",
        "-S",
        "--sort-by",
        help="排序字段: name/count/total_size/avg_size"
    ),
    sort_desc: bool = typer.Option(
        True,
        "--desc/--asc",
        help="降序/升序排序（默认降序）"
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
    no_result_cache: bool = typer.Option(
        False,
        "--no-result-cache",
        help="不保存搜索结果到缓存（用于 --refine）"
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
        
    分组与二次筛选:
    
        # 搜索并按压缩包分组
        findz "ext IN ('jpg', 'png')" /path -A -G archive
        
        # 搜索 + 分组 + 筛选平均大小 > 1M
        findz "ext IN ('jpg', 'png')" /path -A -G archive -R "avg_size > 1M"
        
        # 按扩展名分组，筛选文件数 > 10
        findz "1" /path -G ext -R "count > 10"
        
        # 从缓存加载上次结果进行二次筛选（不提供路径）
        findz -G archive -R "avg_size > 1M"
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
    
    # 纯二次筛选模式：没有 where 和 paths，但有 group_by 或 refine
    if where is None and not paths and (group_by or refine):
        execute_refine(
            filter_expr=refine,
            group_by=group_by,
            sort_by=sort_by,
            sort_desc=sort_desc,
            json_output=json_output,
            long=long,
            save_output=save_output,
            ask_save=ask_save,
            source_files=None,  # 从缓存加载
        )
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
    result_files = execute_search(
        where=where,
        paths=tuple(paths),
        long=long,
        csv_output=csv_output,
        csv_no_head=csv_no_head,
        json_output=json_output if not group_by else False,  # 如果要分组，先不输出 JSON
        archive_separator=archive_separator,
        follow_symlinks=follow_symlinks,
        no_archive=no_archive,
        archives_only=archives_only,
        print_zero=print_zero,
        save_output=save_output if not group_by else None,  # 如果要分组，先不保存
        ask_save=ask_save if not group_by else False,
        continue_on_error=continue_on_error,
        no_cache=no_result_cache,
        silent=bool(group_by),  # 如果要分组，静默搜索
    )
    
    # 如果有分组参数，进行分组和二次筛选
    if group_by and result_files:
        execute_refine(
            filter_expr=refine,
            group_by=group_by,
            sort_by=sort_by,
            sort_desc=sort_desc,
            json_output=json_output,
            long=long,
            save_output=save_output,
            ask_save=ask_save,
            source_files=result_files,
        )


def execute_refine(
    filter_expr: Optional[str],
    group_by: Optional[str],
    sort_by: str,
    sort_desc: bool,
    json_output: bool,
    long: bool,
    save_output: Optional[str],
    ask_save: bool,
    source_files: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    执行二次筛选
    
    Args:
        source_files: 直接传入的文件列表，如果为 None 则从缓存加载
    """
    # 获取文件列表
    if source_files is not None:
        files = source_files
        console.print(f"[dim]处理 {len(files)} 个结果[/dim]")
    else:
        # 从缓存加载
        cache = load_results_cache()
        if not cache:
            console.print("[bold red]错误:[/bold red] 没有找到缓存的搜索结果")
            console.print("[dim]提示: 先执行一次搜索，结果会自动缓存[/dim]")
            return
        
        files = cache.get('files', [])
        metadata = cache.get('metadata', {})
        timestamp = cache.get('timestamp', '')
        
        console.print(f"[dim]加载缓存: {len(files)} 个文件 (搜索于 {timestamp})[/dim]")
        if metadata:
            console.print(f"[dim]原始查询: {metadata.get('where', '')} @ {metadata.get('paths', [])}[/dim]")
    
    # 如果没有分组，直接对文件列表进行筛选
    if not group_by:
        # 简单筛选模式：对文件列表应用过滤
        if filter_expr:
            filter_dict = parse_refine_filter(filter_expr)
            filtered = apply_refine_filter(files, filter_dict)
        else:
            filtered = files
        
        console.print(f"\n[bold cyan]筛选结果: {len(filtered)} 个文件[/bold cyan]\n")
        
        if json_output:
            output = json.dumps(filtered, ensure_ascii=False, indent=2)
            console.print(output)
            _handle_save_output(output, save_output, ask_save, False)
        else:
            output_lines = []
            for f in filtered[:100]:  # 限制显示数量
                if long:
                    line = f"{f.get('date', '')} {f.get('time', '')} {f.get('size_formatted', ''):>10} {f.get('container', '')}//{f.get('path', '')}" if f.get('container') else f"{f.get('date', '')} {f.get('time', '')} {f.get('size_formatted', ''):>10} {f.get('path', '')}"
                else:
                    line = f"{f.get('container', '')}//{f.get('path', '')}" if f.get('container') else f.get('path', '')
                console.print(line)
                output_lines.append(line)
            
            if len(filtered) > 100:
                console.print(f"[dim]... 还有 {len(filtered) - 100} 个文件[/dim]")
            
            _handle_save_output('\n'.join(output_lines), save_output, ask_save, False)
        return
    
    # 分组模式
    if group_by not in ('archive', 'ext', 'dir'):
        console.print(f"[bold red]错误:[/bold red] 不支持的分组字段: {group_by}")
        console.print("[dim]支持: archive(压缩包), ext(扩展名), dir(目录)[/dim]")
        return
    
    # 执行分组
    groups = group_files(files, group_by)
    
    # 应用筛选
    if filter_expr:
        filter_dict = parse_refine_filter(filter_expr)
        groups = apply_refine_filter(groups, filter_dict)
    
    # 排序
    if sort_by in ('name', 'count', 'total_size', 'avg_size'):
        groups.sort(key=lambda x: x.get(sort_by, 0), reverse=sort_desc)
    
    # 统计
    total_files = sum(g['count'] for g in groups)
    total_size = sum(g['total_size'] for g in groups)
    
    group_label = {'archive': '压缩包', 'ext': '扩展名', 'dir': '目录'}[group_by]
    console.print(f"\n[bold cyan]分组结果: {len(groups)} 个{group_label}, {total_files} 个文件, 总计 {format_size(total_size)}[/bold cyan]\n")
    
    if json_output:
        # JSON 输出（不包含 files 列表以减小体积）
        output_groups = [{k: v for k, v in g.items() if k != 'files'} for g in groups]
        output = json.dumps(output_groups, ensure_ascii=False, indent=2)
        console.print(output)
        _handle_save_output(output, save_output, ask_save, False)
    else:
        # 表格输出
        table = Table(show_header=True, header_style="bold")
        table.add_column(group_label, style="cyan")
        table.add_column("数量", justify="right")
        table.add_column("总大小", justify="right")
        table.add_column("平均大小", justify="right", style="yellow")
        
        output_lines = []
        for g in groups[:50]:  # 限制显示数量
            table.add_row(
                g['name'][:50] + ('...' if len(g['name']) > 50 else ''),
                str(g['count']),
                g['total_size_formatted'],
                g['avg_size_formatted'],
            )
            output_lines.append(g['key'])
        
        console.print(table)
        
        if len(groups) > 50:
            console.print(f"[dim]... 还有 {len(groups) - 50} 个分组[/dim]")
        
        # 保存时只保存路径
        _handle_save_output('\n'.join(output_lines), save_output, ask_save, False)


if __name__ == "__main__":
    app()

