# findz - Installation & Development Guide

## Installation

### From Source

```bash
cd src/findz
pip install -e .
```

### With Full Archive Support

```bash
pip install -e ".[full]"
```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip or uv package manager

### Install Development Dependencies

```bash
# Using pip
pip install -e ".[full]"

# Using uv
uv pip install -e ".[full]"
```

### Run Tests

```bash
# Run the example test
python test_example.py
```

### Run findz

```bash
# As a module
python -m findz 'size > 1M'

# Or if installed
findz 'size > 1M'
```

## Project Structure

```
findz/
├── __init__.py          # Package initialization
├── __main__.py          # Entry point for python -m findz
├── cli.py               # Command-line interface
├── filter/              # Filter expression module
│   ├── __init__.py
│   ├── filter.py        # Filter expression evaluation
│   ├── lang.py          # SQL WHERE syntax parser
│   ├── size.py          # Size parsing/formatting
│   └── value.py         # Value types
├── find/                # File finding module
│   ├── __init__.py
│   ├── find.py          # FileInfo and archive support
│   └── walk.py          # File system walking
├── pyproject.toml       # Project configuration
├── README.md            # Main documentation
├── EXAMPLES.md          # Usage examples
├── LICENSE              # MIT License
└── .gitignore          # Git ignore rules
```

## Dependencies

### Required
- **click** - Command-line interface framework
- **pyparsing** - Parser for SQL WHERE syntax
- **rich** - Rich terminal output

### Optional (for full archive support)
- **py7zr** - 7z archive support
- **rarfile** - RAR archive support (also requires unrar)

## Building Distribution

```bash
# Build wheel and sdist
pip install build
python -m build

# Install locally
pip install dist/findz-*.whl
```

## Testing Archive Support

### Test with tar archives
```bash
# Create a test tar.gz
tar -czf test.tar.gz README.md LICENSE

# Search inside
findz 'name = "README.md"' test.tar.gz
```

### Test with zip archives
```bash
# Create a test zip
zip test.zip README.md LICENSE

# Search inside
findz 'archive = "zip"' test.zip
```

## Known Issues

1. **Performance**: Python version may be slower than Go version for large file trees
2. **7z Support**: Requires py7zr package (install with `pip install findz[full]`)
3. **RAR Support**: Requires both rarfile package and unrar utility

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Differences from zfind

This is a faithful port of zfind to Python with these differences:

1. **Parser**: Uses pyparsing instead of participle
2. **CLI**: Uses Click instead of Kong
3. **Performance**: May be slower due to Python vs Go
4. **Archive libs**: Uses Python libraries (tarfile, zipfile, py7zr, rarfile)

## License

MIT License - See LICENSE file for details

## Credits

- Original zfind: Christian Zangl (laktak)
- findz Python port: findz contributors
