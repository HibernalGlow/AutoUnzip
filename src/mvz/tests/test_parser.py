"""Tests for mvz.parser module."""

import pytest
from mvz.parser import ArchiveEntry, parse_line, parse_lines, group_by_archive


class TestParseLine:
    """Tests for parse_line function."""

    def test_simple_archive_path(self):
        """Test parsing simple archive//path format."""
        result = parse_line("D:\\archives\\test.zip//folder/file.txt")
        assert result is not None
        assert result.archive_path == "D:\\archives\\test.zip"
        assert result.internal_path == "folder/file.txt"

    def test_archive_path_with_japanese(self):
        """Test parsing with Japanese characters."""
        result = parse_line("D:\\アーカイブ\\テスト.zip//フォルダ/ファイル.txt")
        assert result is not None
        assert result.archive_path == "D:\\アーカイブ\\テスト.zip"
        assert result.internal_path == "フォルダ/ファイル.txt"

    def test_archive_path_with_chinese(self):
        """Test parsing with Chinese characters."""
        result = parse_line("D:\\归档\\测试.zip//文件夹/文件.txt")
        assert result is not None
        assert result.archive_path == "D:\\归档\\测试.zip"
        assert result.internal_path == "文件夹/文件.txt"

    def test_long_format_line(self):
        """Test parsing long format line with date/size."""
        result = parse_line("2025-01-15 10:30:45      1.5K D:\\path\\archive.zip//file.txt")
        assert result is not None
        assert result.archive_path == "D:\\path\\archive.zip"
        assert result.internal_path == "file.txt"

    def test_non_archive_path(self):
        """Test that non-archive paths return None."""
        result = parse_line("D:\\normal\\path\\file.txt")
        assert result is None

    def test_empty_line(self):
        """Test empty line returns None."""
        result = parse_line("")
        assert result is None
        result = parse_line("   ")
        assert result is None

    def test_custom_separator(self):
        """Test custom separator."""
        result = parse_line("archive.zip::internal/file.txt", separator="::")
        assert result is not None
        assert result.archive_path == "archive.zip"
        assert result.internal_path == "internal/file.txt"


class TestArchiveEntry:
    """Tests for ArchiveEntry dataclass properties."""

    def test_archive_name(self):
        """Test archive_name property."""
        entry = ArchiveEntry(
            archive_path="D:\\path\\test_archive.zip",
            internal_path="folder/file.txt",
            raw_line=""
        )
        assert entry.archive_name == "test_archive"

    def test_archive_ext(self):
        """Test archive_ext property."""
        entry = ArchiveEntry(
            archive_path="D:\\path\\test.7z",
            internal_path="folder/file.txt",
            raw_line=""
        )
        assert entry.archive_ext == "7z"

    def test_internal_name(self):
        """Test internal_name property."""
        entry = ArchiveEntry(
            archive_path="test.zip",
            internal_path="folder/subfolder/image.jpg",
            raw_line=""
        )
        assert entry.internal_name == "image.jpg"

    def test_internal_ext(self):
        """Test internal_ext property."""
        entry = ArchiveEntry(
            archive_path="test.zip",
            internal_path="folder/document.PDF",
            raw_line=""
        )
        assert entry.internal_ext == "pdf"


class TestParseLines:
    """Tests for parse_lines function."""

    def test_multiple_lines(self):
        """Test parsing multiple lines."""
        lines = [
            "archive1.zip//file1.txt",
            "archive2.zip//file2.txt",
            "normal_file.txt",  # Should be skipped
            "archive1.zip//file3.txt",
        ]
        result = parse_lines(lines)
        assert len(result) == 3
        assert result[0].archive_path == "archive1.zip"
        assert result[1].archive_path == "archive2.zip"
        assert result[2].internal_path == "file3.txt"

    def test_empty_list(self):
        """Test empty input list."""
        result = parse_lines([])
        assert result == []


class TestGroupByArchive:
    """Tests for group_by_archive function."""

    def test_grouping(self):
        """Test grouping entries by archive."""
        entries = [
            ArchiveEntry("archive1.zip", "file1.txt", ""),
            ArchiveEntry("archive2.zip", "file2.txt", ""),
            ArchiveEntry("archive1.zip", "file3.txt", ""),
            ArchiveEntry("archive1.zip", "file4.txt", ""),
        ]
        groups = group_by_archive(entries)
        
        assert len(groups) == 2
        assert len(groups["archive1.zip"]) == 3
        assert len(groups["archive2.zip"]) == 1

    def test_empty_list(self):
        """Test grouping empty list."""
        groups = group_by_archive([])
        assert groups == {}
