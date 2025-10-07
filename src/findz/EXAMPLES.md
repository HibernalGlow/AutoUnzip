# findz - Examples

## Basic Examples

```python
# Example 1: Create a filter and test files
from findz import create_filter
from findz.find.find import FileInfo
from datetime import datetime

# Create a filter
filter_expr = create_filter('size > 1M and ext = "zip"')

# Create a FileInfo object
file = FileInfo(
    name="archive.zip",
    path="/path/to/archive.zip",
    mod_time=datetime.now(),
    size=5_000_000,
    file_type="file"
)

# Test if the file matches
matches, error = filter_expr.test(file.context())
if matches:
    print(f"File {file.name} matches the filter!")
```

## CLI Usage

```bash
# Find all Python files
findz 'ext = "py"'

# Find large files (> 10MB)
findz 'size > 10M'

# Find files modified today
findz 'date = today'

# Find files in archives
findz 'archive = "zip"'

# Complex query
findz 'name like "test%" and size < 1K and date > "2024-01-01"'

# Output in CSV format
findz 'type = "file"' --csv

# Long listing format
findz 'size > 1M' -l

# Search specific paths
findz 'ext = "log"' /var/log /tmp
```

## Filter Syntax Examples

### Size Filters
```bash
findz 'size < 1K'          # Less than 1 kilobyte
findz 'size = 100M'        # Exactly 100 megabytes
findz 'size >= 1G'         # 1 gigabyte or larger
findz 'size between 10M and 100M'
```

### Name Filters
```bash
findz 'name = "README.md"'
findz 'name like "test%"'   # Starts with "test"
findz 'name like "%log"'    # Ends with "log"
findz 'name like "%temp%"'  # Contains "temp"
findz 'name ilike "README%"' # Case-insensitive
findz 'name rlike "^[0-9]+\\.txt$"' # Regex match
```

### Date/Time Filters
```bash
findz 'date = today'
findz 'date = mo'          # Last Monday
findz 'date > "2024-01-01"'
findz 'date < "2024"'
findz 'date between "2024-01-01" and "2024-12-31"'
findz 'time > "12:00:00"'
```

### Type Filters
```bash
findz 'type = "file"'
findz 'type = "dir"'
findz 'type = "link"'
findz 'type in ("file", "link")'
```

### Extension Filters
```bash
findz 'ext = "py"'
findz 'ext in ("jpg", "png", "gif")'
findz 'ext2 = "tar.gz"'    # Two-part extension
```

### Archive Filters
```bash
findz 'archive = "zip"'
findz 'archive in ("tar", "zip")'
findz 'container like "%.tar.gz"'
findz 'archive <> ""'      # Any file in an archive
```

### Logical Operators
```bash
findz 'size > 1M and ext = "log"'
findz 'name like "%.py" or name like "%.js"'
findz 'not (type = "dir")'
findz '(size < 1K or size > 1G) and date = today'
```

## Programmatic Usage

```python
from findz.find.walk import walk, WalkParams
from findz import create_filter

# Create filter
filter_expr = create_filter('size > 1M')

# Set up parameters
params = WalkParams(
    filter_expr=filter_expr,
    follow_symlinks=False,
    no_archive=False,
    error_handler=lambda msg: print(f"Error: {msg}")
)

# Walk directory and find matching files
for file_info in walk("/path/to/search", params):
    print(f"{file_info.path} - {file_info.size} bytes")
```

## Advanced Examples

### Find duplicate filenames
```bash
findz 'name = "config.json"' --csv | cut -d, -f2
```

### Find large log files modified recently
```bash
findz 'ext = "log" and size > 10M and date >= mo'
```

### Find Python files excluding tests
```bash
findz 'ext = "py" and not (name like "test%")'
```

### Find files in multiple archive types
```bash
findz 'archive in ("zip", "tar") and size < 1M'
```

### Search with null-terminated output (for xargs)
```bash
findz 'size > 100M' -0 | xargs -0 ls -lh
```
