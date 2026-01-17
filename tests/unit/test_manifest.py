"""Tests for manifest handling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from harness_bench.core.manifest import (
    Manifest,
    HarnessInfo,
    TaskInfo,
    RunInfo,
    EnvironmentInfo,
    RunStatus,
)


class TestHarnessInfo:
    """Test HarnessInfo dataclass."""

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields."""
        info = HarnessInfo(id="test-harness")
        d = info.to_dict()

        assert d == {"id": "test-harness"}

    def test_to_dict_full(self):
        """Test to_dict with all fields."""
        info = HarnessInfo(
            id="test-harness",
            version="1.0.0",
            vendor="test-vendor",
            model="test-model",
            config={"key": "value"},
        )
        d = info.to_dict()

        assert d == {
            "id": "test-harness",
            "version": "1.0.0",
            "vendor": "test-vendor",
            "model": "test-model",
            "config": {"key": "value"},
        }

    def test_from_dict(self):
        """Test from_dict round-trip."""
        original = HarnessInfo(
            id="test-harness",
            version="1.0.0",
            vendor="test-vendor",
        )

        reconstructed = HarnessInfo.from_dict(original.to_dict())

        assert reconstructed.id == original.id
        assert reconstructed.version == original.version
        assert reconstructed.vendor == original.vendor


class TestTaskInfo:
    """Test TaskInfo dataclass."""

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields."""
        info = TaskInfo(id="TEST-01")
        d = info.to_dict()

        assert d == {"id": "TEST-01"}

    def test_to_dict_full(self):
        """Test to_dict with all fields."""
        info = TaskInfo(
            id="TEST-01",
            name="Test Task",
            domain="test",
            level=2,
        )
        d = info.to_dict()

        assert d == {
            "id": "TEST-01",
            "name": "Test Task",
            "domain": "test",
            "level": 2,
        }

    def test_from_dict(self):
        """Test from_dict round-trip."""
        original = TaskInfo(id="TEST-01", name="Test Task", level=3)
        reconstructed = TaskInfo.from_dict(original.to_dict())

        assert reconstructed.id == original.id
        assert reconstructed.name == original.name
        assert reconstructed.level == original.level


class TestRunInfo:
    """Test RunInfo dataclass."""

    def test_default_status(self):
        """Test default status is PENDING."""
        info = RunInfo(id="run_123")
        assert info.status == RunStatus.PENDING

    def test_to_dict(self):
        """Test to_dict with timestamps."""
        now = datetime.now(timezone.utc)
        info = RunInfo(
            id="run_123",
            status=RunStatus.COMPLETED,
            started_at=now,
            completed_at=now,
        )
        d = info.to_dict()

        assert d["id"] == "run_123"
        assert d["status"] == "completed"
        assert "started_at" in d
        assert "completed_at" in d

    def test_from_dict_parses_iso_timestamps(self):
        """Test from_dict parses ISO timestamps."""
        data = {
            "id": "run_123",
            "status": "in_progress",
            "started_at": "2024-01-15T10:30:00+00:00",
        }
        info = RunInfo.from_dict(data)

        assert info.id == "run_123"
        assert info.status == RunStatus.IN_PROGRESS
        assert info.started_at is not None
        assert info.started_at.year == 2024


class TestEnvironmentInfo:
    """Test EnvironmentInfo dataclass."""

    def test_to_dict(self):
        """Test to_dict."""
        info = EnvironmentInfo(
            os="linux",
            arch="x86_64",
            python_version="3.10.0",
        )
        d = info.to_dict()

        assert d == {
            "os": "linux",
            "arch": "x86_64",
            "python_version": "3.10.0",
        }

    def test_from_dict_with_extra_fields(self):
        """Test from_dict preserves extra fields."""
        data = {
            "os": "linux",
            "arch": "x86_64",
            "python_version": "3.10.0",
            "custom_field": "custom_value",
        }
        info = EnvironmentInfo.from_dict(data)

        assert info.os == "linux"
        assert info.extra["custom_field"] == "custom_value"


class TestManifest:
    """Test Manifest dataclass."""

    def test_roundtrip_json(self, sample_manifest: dict):
        """Test JSON round-trip serialization."""
        manifest = Manifest.from_dict(sample_manifest)
        json_str = manifest.to_json()
        reconstructed = Manifest.from_json(json_str)

        assert reconstructed.protocol_version == manifest.protocol_version
        assert reconstructed.harness.id == manifest.harness.id
        assert reconstructed.task.id == manifest.task.id
        assert reconstructed.run.id == manifest.run.id

    def test_save_and_load(self, git_workspace: Path, sample_manifest: dict):
        """Test save and load to/from workspace."""
        manifest = Manifest.from_dict(sample_manifest)

        # Save
        saved_path = manifest.save(git_workspace)
        assert saved_path.exists()
        assert saved_path == git_workspace / ".harness-bench" / "manifest.json"

        # Load
        loaded = Manifest.load(git_workspace)
        assert loaded.protocol_version == manifest.protocol_version
        assert loaded.harness.id == manifest.harness.id

    def test_load_missing_raises(self, temp_dir: Path):
        """Test loading missing manifest raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            Manifest.load(temp_dir)

    def test_get_branch_name(self, sample_manifest: dict):
        """Test branch name generation."""
        manifest = Manifest.from_dict(sample_manifest)
        branch = manifest.get_branch_name()

        assert branch == "harness/test-harness/TEST-01/run_12345"

    def test_mark_started(self, sample_manifest: dict):
        """Test mark_started updates status and timestamp."""
        manifest = Manifest.from_dict(sample_manifest)
        assert manifest.run.status == RunStatus.PENDING
        assert manifest.run.started_at is None

        manifest.mark_started()

        assert manifest.run.status == RunStatus.IN_PROGRESS
        assert manifest.run.started_at is not None

    def test_mark_completed_success(self, sample_manifest: dict):
        """Test mark_completed with success=True."""
        manifest = Manifest.from_dict(sample_manifest)
        manifest.mark_started()

        manifest.mark_completed(success=True)

        assert manifest.run.status == RunStatus.COMPLETED
        assert manifest.run.completed_at is not None

    def test_mark_completed_failure(self, sample_manifest: dict):
        """Test mark_completed with success=False."""
        manifest = Manifest.from_dict(sample_manifest)
        manifest.mark_started()

        manifest.mark_completed(success=False)

        assert manifest.run.status == RunStatus.FAILED

    def test_mark_timeout(self, sample_manifest: dict):
        """Test mark_timeout."""
        manifest = Manifest.from_dict(sample_manifest)
        manifest.mark_started()

        manifest.mark_timeout()

        assert manifest.run.status == RunStatus.TIMEOUT
        assert manifest.run.completed_at is not None


class TestRunStatus:
    """Test RunStatus enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses are defined."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.IN_PROGRESS.value == "in_progress"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.TIMEOUT.value == "timeout"

    def test_status_from_string(self):
        """Test creating status from string."""
        status = RunStatus("completed")
        assert status == RunStatus.COMPLETED
