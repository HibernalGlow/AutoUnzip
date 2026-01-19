"""Tests for mvz.executor module."""

import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from mvz.executor import (
    find_7z,
    run_7z,
    delete_files,
    rename_file,
    extract_files,
    batch_rename,
)


@pytest.fixture
def temp_archive():
    """Create a temporary ZIP archive for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "test_archive.zip"
        
        # Create a ZIP with some test files
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("file1.txt", "content of file 1")
            zf.writestr("file2.txt", "content of file 2")
            zf.writestr("folder/file3.txt", "content of file 3")
            zf.writestr("日本語/テスト.txt", "Japanese content")
            zf.writestr("中文/测试.txt", "Chinese content")
        
        yield str(archive_path)


class TestFind7z:
    """Tests for find_7z function."""

    def test_find_7z(self):
        """Test that 7z can be found (if installed)."""
        result = find_7z()
        # This might fail on systems without 7z installed
        # We'll skip if not found
        if result is None:
            pytest.skip("7z not installed on this system")
        assert os.path.isfile(result)


class TestRun7z:
    """Tests for run_7z function."""

    def test_run_7z_version(self):
        """Test running 7z with --help."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        retcode, stdout, stderr = run_7z(["--help"])
        # 7z returns 0 for help
        assert retcode == 0 or "7-Zip" in stdout


class TestDeleteFiles:
    """Tests for delete_files function."""

    def test_dry_run(self, temp_archive):
        """Test delete in dry run mode."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        result = delete_files(temp_archive, ["file1.txt"], dry_run=True)
        assert result.success
        assert "[DRY RUN]" in result.message
        
        # Verify file still exists
        with zipfile.ZipFile(temp_archive, "r") as zf:
            assert "file1.txt" in zf.namelist()

    def test_actual_delete(self, temp_archive):
        """Test actual file deletion."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        result = delete_files(temp_archive, ["file1.txt"], dry_run=False)
        assert result.success
        
        # Verify file was deleted
        with zipfile.ZipFile(temp_archive, "r") as zf:
            assert "file1.txt" not in zf.namelist()
            assert "file2.txt" in zf.namelist()  # Other files still exist

    def test_delete_nonexistent_archive(self):
        """Test deleting from nonexistent archive."""
        result = delete_files("nonexistent.zip", ["file.txt"], dry_run=False)
        assert not result.success
        assert "not found" in result.message.lower()


class TestRenameFile:
    """Tests for rename_file function."""

    def test_dry_run(self, temp_archive):
        """Test rename in dry run mode."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        result = rename_file(temp_archive, "file1.txt", "renamed.txt", dry_run=True)
        assert result.success
        assert "[DRY RUN]" in result.message
        
        # Verify file still has old name
        with zipfile.ZipFile(temp_archive, "r") as zf:
            assert "file1.txt" in zf.namelist()
            assert "renamed.txt" not in zf.namelist()

    def test_actual_rename(self, temp_archive):
        """Test actual file rename."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        result = rename_file(temp_archive, "file1.txt", "renamed.txt", dry_run=False)
        assert result.success
        
        # Verify rename
        with zipfile.ZipFile(temp_archive, "r") as zf:
            assert "file1.txt" not in zf.namelist()
            assert "renamed.txt" in zf.namelist()


class TestExtractFiles:
    """Tests for extract_files function."""

    def test_dry_run(self, temp_archive):
        """Test extract in dry run mode."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        with tempfile.TemporaryDirectory() as outdir:
            result = extract_files(temp_archive, ["file1.txt"], outdir, dry_run=True)
            assert result.success
            assert "[DRY RUN]" in result.message
            
            # Verify file was not extracted
            assert not os.path.exists(os.path.join(outdir, "file1.txt"))

    def test_actual_extract(self, temp_archive):
        """Test actual file extraction."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        with tempfile.TemporaryDirectory() as outdir:
            result = extract_files(temp_archive, ["file1.txt"], outdir, dry_run=False)
            assert result.success
            
            # Verify extraction
            extracted = os.path.join(outdir, "file1.txt")
            assert os.path.exists(extracted)
            with open(extracted, "r") as f:
                assert f.read() == "content of file 1"

    def test_extract_with_flatten(self, temp_archive):
        """Test extraction with flatten option."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        with tempfile.TemporaryDirectory() as outdir:
            result = extract_files(temp_archive, ["folder/file3.txt"], outdir, dry_run=False, flatten=True)
            assert result.success
            
            # With flatten, file should be directly in outdir
            assert os.path.exists(os.path.join(outdir, "file3.txt"))


class TestBatchRename:
    """Tests for batch_rename function."""

    def test_batch_rename(self, temp_archive):
        """Test batch rename."""
        if find_7z() is None:
            pytest.skip("7z not installed")
        
        pairs = [
            ("file1.txt", "new1.txt"),
            ("file2.txt", "new2.txt"),
        ]
        result = batch_rename(temp_archive, pairs, dry_run=False)
        assert result.success
        
        # Verify renames
        with zipfile.ZipFile(temp_archive, "r") as zf:
            names = zf.namelist()
            assert "file1.txt" not in names
            assert "file2.txt" not in names
            assert "new1.txt" in names
            assert "new2.txt" in names
