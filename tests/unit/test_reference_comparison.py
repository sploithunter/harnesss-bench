"""Regression tests for reference_comparison verification.

Verifies that _verify_reference_comparison actually compares outputs
instead of returning hardcoded success (issue #4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_bench.evaluation.evaluator import Evaluator


class TestVerifyReferenceComparison:
    """Tests for Evaluator._verify_reference_comparison."""

    def test_incorrect_candidate_fails(self, temp_dir: Path):
        """Incorrect candidate output must fail verification.

        This is the core regression test for issue #4: previously,
        _verify_reference_comparison always returned success=True.
        """
        (temp_dir / "reference.py").write_text('print("hello world")\n')
        (temp_dir / "candidate.py").write_text('print("wrong output")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.method == "reference_comparison"
        assert result.success is False
        assert result.score == 0.0
        assert result.details["match"] is False

    def test_correct_candidate_passes(self, temp_dir: Path):
        """Candidate producing matching output should pass."""
        (temp_dir / "reference.py").write_text('print("hello world")\n')
        (temp_dir / "candidate.py").write_text('print("hello world")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.method == "reference_comparison"
        assert result.success is True
        assert result.score == 1.0
        assert result.details["match"] is True

    def test_missing_reference_fails(self, temp_dir: Path):
        """Should fail when reference file doesn't exist."""
        (temp_dir / "candidate.py").write_text('print("hello")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "nonexistent.py",
            "entry_point": "candidate.py",
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert "not found" in result.details["error"].lower()

    def test_missing_candidate_fails(self, temp_dir: Path):
        """Should fail when candidate file doesn't exist."""
        (temp_dir / "reference.py").write_text('print("hello")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "nonexistent.py",
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert "not found" in result.details["error"].lower()

    def test_no_reference_or_expected_output_fails(self, temp_dir: Path):
        """Should fail when neither reference nor expected_output is specified."""
        (temp_dir / "candidate.py").write_text('print("hello")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "entry_point": "candidate.py",
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert "error" in result.details

    def test_no_entry_point_fails(self, temp_dir: Path):
        """Should fail when no entry_point is specified."""
        (temp_dir / "reference.py").write_text('print("hello")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert "entry_point" in result.details["error"].lower()

    def test_expected_output_file_match(self, temp_dir: Path):
        """Should pass when candidate output matches expected output file."""
        (temp_dir / "expected.txt").write_text("hello world\n")
        (temp_dir / "candidate.py").write_text('print("hello world")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "expected_output": "expected.txt",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is True
        assert result.score == 1.0

    def test_expected_output_file_mismatch(self, temp_dir: Path):
        """Should fail when candidate output doesn't match expected output file."""
        (temp_dir / "expected.txt").write_text("hello world\n")
        (temp_dir / "candidate.py").write_text('print("wrong output")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "expected_output": "expected.txt",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert result.score == 0.0

    def test_candidate_crash_fails(self, temp_dir: Path):
        """Should fail when candidate script crashes."""
        (temp_dir / "reference.py").write_text('print("hello")\n')
        (temp_dir / "candidate.py").write_text('raise RuntimeError("crash")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert result.score == 0.0

    def test_reference_crash_fails(self, temp_dir: Path):
        """Should fail when reference script crashes."""
        (temp_dir / "reference.py").write_text('raise RuntimeError("crash")\n')
        (temp_dir / "candidate.py").write_text('print("hello")\n')

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is False
        assert result.score == 0.0

    def test_multiline_output_comparison(self, temp_dir: Path):
        """Should correctly compare multi-line outputs."""
        (temp_dir / "reference.py").write_text(
            'print("line 1")\nprint("line 2")\nprint("line 3")\n'
        )
        (temp_dir / "candidate.py").write_text(
            'print("line 1")\nprint("line 2")\nprint("line 3")\n'
        )

        evaluator = Evaluator(workspace=temp_dir)
        config = {
            "method": "reference_comparison",
            "reference": "reference.py",
            "entry_point": "candidate.py",
            "timeout_seconds": 10,
        }

        result = evaluator._verify_reference_comparison(config)

        assert result.success is True
        assert result.score == 1.0
