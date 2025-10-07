# findz

A Python port of [zfind](https://github.com/laktak/zfind) - search for files with SQL-like WHERE syntax.

`findz` allows you to search for files, including inside `tar`, `zip`, `7z` and `rar` archives. It makes finding files easy with a filter syntax that is similar to an SQL-WHERE clause.

## Features

- 🔍 **SQL-like WHERE clause** - Familiar syntax for filtering files
- 📦 **Archive support** - Search inside tar, zip, 7z, and rar archives
- 🎯 **Flexible filtering** - Filter by name, size, date, type, extension, and more
- 📊 **Multiple output formats** - Plain text, long listing, or CSV
- 🔗 **Symlink support** - Optionally follow symbolic links
- 🎨 **Rich terminal output** - Beautiful, colorful output

## Installation

```bash
# Basic installation
pip install findz

# With full archive support (7z and rar)
pip install findz[full]
```

## Quick Start

```bash
# Find files smaller than 10KB
findz 'size<10k'

# Find files in the given range
findz 'size between 1M and 1G' /some/path

# Find files modified before 2010 inside a tar
findz 'date<"2010" and archive="tar"'

# Find files named foo* and modified today
findz 'name like "foo%" and date=today'

# Find files that contain two dashes using a regex
findz 'name rlike "(.*-){2}"'

# Find files with extension .jpg or .jpeg
findz 'ext in ("jpg","jpeg")'

# Find directories named foo and bar
findz 'name in ("foo", "bar") and type="dir"'

# Show results in long listing format
findz 'name="README.md"' -l

# Show results in CSV format
findz 'size>1M' --csv
```

## WHERE Syntax

### Logical Operators

- `AND`, `OR` - Combine multiple conditions
- `NOT` - Negate a condition
- `()` - Group conditions

Example: `'(size > 20M OR name = "temp") AND type="file"'`

### Comparison Operators

- `=`, `<>`, `!=` - Equal, not equal
- `<`, `>`, `<=`, `>=` - Less than, greater than, etc.

Example: `'date > "2020-10-01"'`

### Pattern Matching

- `LIKE` - Case-sensitive pattern matching with `%` (any chars) and `_` (single char)
- `ILIKE` - Case-insensitive pattern matching
- `RLIKE` - Regular expression matching

Example: `'name like "z%"'` (names starting with 'z')

### Other Operators

- `IN` - Match against multiple values
- `BETWEEN` - Range matching (inclusive)

Example: `'ext in ("jpg", "png", "gif")'`

### Values

- **Numbers**: `42`, `3.14`, `-10`
- **Sizes**: Append `B`, `K`, `M`, `G`, `T` for bytes, KB, MB, GB, TB
  - Examples: `10K`, `1.5M`, `2G`
- **Text**: Single or double quoted strings
  - Examples: `"hello"`, `'world'`
- **Dates**: `YYYY-MM-DD` format
  - Examples: `"2024-01-01"`, `"2023-12"`
- **Times**: 24-hour `HH:MM:SS` format
  - Examples: `"14:30:00"`, `"09:00"`
- **Booleans**: `TRUE`, `FALSE`

## File Properties

### Basic Properties

- `name` - Name of the file
- `path` - Full path of the file
- `size` - File size in bytes (uncompressed)
- `date` - Modified date (YYYY-MM-DD format)
- `time` - Modified time (HH:MM:SS format)
- `ext` - Short file extension (e.g., 'txt')
- `ext2` - Long file extension (e.g., 'tar.gz')
- `type` - File type: `file`, `dir`, or `link`

### Archive Properties

- `archive` - Archive type if inside a container: `tar`, `zip`, `7z`, or `rar`
- `container` - Path of the container archive (if any)

### Helper Properties

- `today` - Today's date
- `mo`, `tu`, `we`, `th`, `fr`, `sa`, `su` - Last occurrence of each weekday

## Command-Line Options

```
Usage: findz [OPTIONS] [WHERE] [PATHS]...

Options:
  -H, --filter-help           Show where-filter help
  -l, --long                  Show long listing format
  --csv                       Show listing as CSV
  --csv-no-head              Show listing as CSV without header
  --archive-separator TEXT    Separator between archive and file (default: //)
  -L, --follow-symlinks       Follow symbolic links
  -n, --no-archive           Disable archive support
  -0, --print0               Use null character instead of newline
  -V, --version              Show version
  --help                     Show this message and exit
```

## Examples

### Find large files

```bash
# Files larger than 100MB
findz 'size > 100M'

# Files between 10MB and 1GB
findz 'size between 10M and 1G'
```

### Find by date

```bash
# Files modified today
findz 'date = today'

# Files modified last week
findz 'date >= mo'

# Files modified before 2020
findz 'date < "2020-01-01"'
```

### Search in archives

```bash
# All files in zip archives
findz 'archive = "zip"'

# Large files in any archive
findz 'size > 10M and archive <> ""'

# Python files in tar.gz archives
findz 'ext = "py" and container like "%.tar.gz"'
```

### Complex queries

```bash
# Python or JavaScript files larger than 1KB
findz 'ext in ("py", "js") and size > 1K'

# Recently modified config files
findz 'name like "%.conf" and date >= mo'

# Find duplicate file names
findz 'name = "config.json"' --csv
```

## Archive Support

### Built-in Support

- **tar** - Including .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz, .txz
- **zip** - Standard ZIP archives

### Optional Support

Install with `pip install findz[full]` for:

- **7z** - 7-Zip archives (requires py7zr)
- **rar** - RAR archives (requires rarfile and unrar)

## Differences from zfind

This is a faithful Python port of the original Go-based zfind, with the following notes:

- Performance may differ due to language differences
- Some error messages may be phrased differently
- Archive handling uses Python libraries instead of Go libraries
- CLI uses Click instead of Kong for argument parsing

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.

## Credits

This project is a Python port of [zfind](https://github.com/laktak/zfind) by Christian Zangl.

Original zfind: © Christian Zangl (laktak)
findz (Python port): © findz contributors

## Related Projects

- [zfind](https://github.com/laktak/zfind) - The original Go implementation
