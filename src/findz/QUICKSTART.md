# findz - Quick Start Guide

## 🚀 Quick Installation

```bash
cd src/findz
pip install -e .
```

## 🎯 Basic Usage

### 1. Find files by size
```bash
# Files smaller than 10KB
findz 'size < 10K'

# Files larger than 1MB
findz 'size > 1M'

# Files between 10MB and 100MB
findz 'size between 10M and 100M'
```

### 2. Find files by name
```bash
# Exact name
findz 'name = "README.md"'

# Pattern matching (starts with "test")
findz 'name like "test%"'

# Case-insensitive
findz 'name ilike "readme%"'
```

### 3. Find files by date
```bash
# Modified today
findz 'date = today'

# Modified last Monday
findz 'date = mo'

# Modified after a specific date
findz 'date > "2024-01-01"'
```

### 4. Find files by extension
```bash
# Python files
findz 'ext = "py"'

# Image files
findz 'ext in ("jpg", "png", "gif")'

# Tar archives
findz 'ext2 = "tar.gz"'
```

### 5. Find files by type
```bash
# Only files
findz 'type = "file"'

# Only directories
findz 'type = "dir"'

# Files or links
findz 'type in ("file", "link")'
```

### 6. Search in archives
```bash
# Files in ZIP archives
findz 'archive = "zip"'

# Large files in any archive
findz 'size > 1M and archive <> ""'

# Python files in tar.gz archives
findz 'ext = "py" and container like "%.tar.gz"'
```

### 7. Complex queries
```bash
# Large Python files modified today
findz 'ext = "py" and size > 10K and date = today'

# Config files (json or yaml)
findz 'ext in ("json", "yaml", "yml") and name like "%config%"'

# Not directories, and recently modified
findz 'type <> "dir" and date >= mo'
```

## 📊 Output Formats

### Plain text (default)
```bash
findz 'size > 1M'
```

### Long listing (-l)
```bash
findz 'size > 1M' -l
# Output: 2024-10-08 10:30:45    5.2M /path/to/file
```

### CSV format
```bash
findz 'ext = "py"' --csv
# Output: name,path,container,size,date,time,ext,ext2,type,archive
```

### CSV without header
```bash
findz 'ext = "py"' --csv-no-head
```

### Null-terminated (for xargs)
```bash
findz 'size > 100M' -0 | xargs -0 ls -lh
```

## 🔧 Command-Line Options

```bash
-H, --filter-help        Show WHERE syntax help
-l, --long              Long listing format
--csv                   CSV output with header
--csv-no-head           CSV output without header
-L, --follow-symlinks   Follow symbolic links
-n, --no-archive        Don't search in archives
-0, --print0            Null-terminated output
-V, --version           Show version
```

## 📂 Search Paths

```bash
# Current directory (default)
findz 'size > 1M'

# Specific directory
findz 'ext = "log"' /var/log

# Multiple directories
findz 'name = "config"' /etc /home/user/.config
```

## 🎓 Learning More

- Run `findz -H` for full WHERE syntax help
- See `README.md` for complete documentation
- Check `EXAMPLES.md` for more examples
- Read `INSTALL.md` for installation details

## 💡 Pro Tips

1. **Use quotes** around the WHERE clause:
   ```bash
   findz 'size > 1M'  # Good
   findz size > 1M    # May not work in some shells
   ```

2. **Size units** are case-insensitive:
   ```bash
   findz 'size > 10M'  # OK
   findz 'size > 10m'  # Also OK
   ```

3. **Pattern matching** with LIKE:
   - `%` matches any characters
   - `_` matches a single character
   ```bash
   findz 'name like "test_%.txt"'
   ```

4. **Regular expressions** with RLIKE:
   ```bash
   findz 'name rlike "^[0-9]+\\.log$"'
   ```

5. **Combine filters** with AND/OR:
   ```bash
   findz '(size < 1K or size > 1G) and type = "file"'
   ```

## 🐛 Troubleshooting

### Archive support not working?
```bash
# Install with full support
pip install -e ".[full]"
```

### No files found?
- Check your WHERE clause syntax with `-H`
- Try simpler filters first: `findz '1'` (matches all)
- Use `-L` to follow symlinks if needed

### Slow performance?
- Use `-n` to disable archive scanning
- Be more specific with your WHERE clause
- Search in specific directories, not root

## 🎉 You're Ready!

Start finding files with SQL-like queries:
```bash
findz 'size > 10M and date >= mo'
```

Happy searching! 🔍
