"""Integration test for mvz CLI."""

import sys
import os
import tempfile
import zipfile

sys.path.insert(0, 'src')

# Create a test archive
with tempfile.TemporaryDirectory() as tmpdir:
    archive_path = os.path.join(tmpdir, 'test.zip')
    
    with zipfile.ZipFile(archive_path, 'w') as zf:
        zf.writestr('file1.txt', 'content 1')
        zf.writestr('file2.jpeg', 'image data')
        zf.writestr('folder/file3.txt', 'content 3')
    
    # Simulate findz output
    findz_output = f"""
{archive_path}//file1.txt
{archive_path}//file2.jpeg
{archive_path}//folder/file3.txt
"""
    
    print('Created test archive with files:')
    with zipfile.ZipFile(archive_path, 'r') as zf:
        for name in zf.namelist():
            print(f'  {name}')
    
    # Test parsing
    from mvz.parser import parse_lines, group_by_archive
    entries = parse_lines(findz_output.strip().split('\n'))
    print(f'\nParsed {len(entries)} entries')
    
    groups = group_by_archive(entries)
    print(f'Grouped into {len(groups)} archive(s)')
    
    # Test rename (dry run)
    from mvz.executor import batch_rename
    pairs = [('file2.jpeg', 'file2.jpg')]
    result = batch_rename(archive_path, pairs, dry_run=False)
    print(f'\nRename .jpeg -> .jpg: {"PASS" if result.success else "FAIL"}')
    
    with zipfile.ZipFile(archive_path, 'r') as zf:
        names = zf.namelist()
        print('Archive contents after rename:')
        for name in names:
            print(f'  {name}')

print('\nCLI integration test complete!')
