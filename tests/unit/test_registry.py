"""Tests for task registry path traversal fix (issue #3)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from harness_bench.tasks.registry import TaskRegistry, TaskEntry, TaskIndex


@pytest.fixture
def registry_with_task(temp_dir: Path):
    """Create a TaskRegistry with a mocked index containing one task."""
    registry = TaskRegistry(base_url="http://localhost:9999", cache_dir=temp_dir / "cache")
    index = TaskIndex(
        version="1.0",
        updated_at="2026-01-01",
        tasks=[
            TaskEntry(
                id="MALICIOUS-01",
                name="Malicious Task",
                domain="general",
                level=1,
                language="python",
                path="MALICIOUS-01",
            )
        ],
    )
    registry._index = index
    return registry


class TestValidatePath:
    """Tests for _validate_path."""

    def test_safe_filename(self, temp_dir: Path):
        """Normal filenames should pass validation."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        TaskRegistry._validate_path("TASK.md", temp_dir)

    def test_safe_subdirectory(self, temp_dir: Path):
        """Filenames in subdirectories should pass validation."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        TaskRegistry._validate_path("src/main.py", temp_dir)

    def test_traversal_rejected(self, temp_dir: Path):
        """Paths with .. that escape output_dir should be rejected."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="Path traversal detected"):
            TaskRegistry._validate_path("../../etc/passwd", temp_dir)

    def test_single_dot_dot_rejected(self, temp_dir: Path):
        """Even a single .. escaping the directory should be rejected."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="Path traversal detected"):
            TaskRegistry._validate_path("../outside.txt", temp_dir)

    def test_absolute_path_rejected(self, temp_dir: Path):
        """Absolute paths should be rejected."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="Absolute path not allowed"):
            TaskRegistry._validate_path("/etc/passwd", temp_dir)

    def test_dot_dot_in_middle_safe(self, temp_dir: Path):
        """Paths with .. that still resolve inside output_dir are ok."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        # "sub/../file.txt" resolves to "file.txt" which is still inside output_dir
        TaskRegistry._validate_path("sub/../file.txt", temp_dir)

    def test_dot_dot_escaping_via_nested(self, temp_dir: Path):
        """Paths that use nested .. to escape should be rejected."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="Path traversal detected"):
            TaskRegistry._validate_path("a/b/../../../../outside.txt", temp_dir)


class TestDownloadTaskPathTraversal:
    """Regression tests for issue #3: path traversal in download_task."""

    def test_malicious_prompt_file_rejected(self, registry_with_task, temp_dir: Path):
        """download_task should reject prompt_file with path traversal."""
        output_dir = temp_dir / "output" / "MALICIOUS-01"

        malicious_task_yaml = textwrap.dedent("""\
            id: MALICIOUS-01
            name: Malicious Task
            prompt_file: ../../outside_prompt.md
            starter_files: []
        """)

        def mock_fetch(url):
            if url.endswith("task.yaml"):
                return malicious_task_yaml
            return "content"

        with patch.object(registry_with_task, "_fetch_url", side_effect=mock_fetch):
            with pytest.raises(ValueError, match="Path traversal detected"):
                registry_with_task.download_task("MALICIOUS-01", output_dir=output_dir)

        # Verify no file was written outside output_dir
        escaped_file = temp_dir / "output" / "outside_prompt.md"
        assert not escaped_file.exists()

    def test_malicious_starter_file_rejected(self, registry_with_task, temp_dir: Path):
        """download_task should reject starter_files with path traversal."""
        output_dir = temp_dir / "output" / "MALICIOUS-01"

        malicious_task_yaml = textwrap.dedent("""\
            id: MALICIOUS-01
            name: Malicious Task
            prompt_file: TASK.md
            starter_files:
              - ../../outside_starter.py
        """)

        def mock_fetch(url):
            if url.endswith("task.yaml"):
                return malicious_task_yaml
            return "content"

        with patch.object(registry_with_task, "_fetch_url", side_effect=mock_fetch):
            with pytest.raises(ValueError, match="Path traversal detected"):
                registry_with_task.download_task("MALICIOUS-01", output_dir=output_dir)

        # Verify no file was written outside output_dir
        escaped_file = temp_dir / "output" / "outside_starter.py"
        assert not escaped_file.exists()

    def test_malicious_absolute_prompt_rejected(self, registry_with_task, temp_dir: Path):
        """download_task should reject absolute prompt_file paths."""
        output_dir = temp_dir / "output" / "MALICIOUS-01"

        malicious_task_yaml = textwrap.dedent("""\
            id: MALICIOUS-01
            name: Malicious Task
            prompt_file: /tmp/evil_prompt.md
            starter_files: []
        """)

        def mock_fetch(url):
            if url.endswith("task.yaml"):
                return malicious_task_yaml
            return "content"

        with patch.object(registry_with_task, "_fetch_url", side_effect=mock_fetch):
            with pytest.raises(ValueError, match="Absolute path not allowed"):
                registry_with_task.download_task("MALICIOUS-01", output_dir=output_dir)

    def test_safe_task_downloads_normally(self, registry_with_task, temp_dir: Path):
        """download_task should work fine with safe filenames."""
        output_dir = temp_dir / "output" / "MALICIOUS-01"

        safe_task_yaml = textwrap.dedent("""\
            id: MALICIOUS-01
            name: Safe Task
            prompt_file: TASK.md
            starter_files:
              - src/main.py
              - config.json
        """)

        def mock_fetch(url):
            if url.endswith("task.yaml"):
                return safe_task_yaml
            if url.endswith("constraints.yaml"):
                from urllib.error import HTTPError
                raise HTTPError(url, 404, "Not found", {}, None)
            return "content"

        with patch.object(registry_with_task, "_fetch_url", side_effect=mock_fetch):
            result = registry_with_task.download_task("MALICIOUS-01", output_dir=output_dir)

        assert result == output_dir
        assert (output_dir / "task.yaml").exists()
        assert (output_dir / "TASK.md").exists()
        assert (output_dir / "src" / "main.py").exists()
        assert (output_dir / "config.json").exists()
