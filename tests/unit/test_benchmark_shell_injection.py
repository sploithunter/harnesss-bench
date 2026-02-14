"""Regression tests for shell injection in benchmark runners (issue #6).

Both run_dds_benchmark.py and run_metr_benchmark.py previously used
os.system() with unquoted string interpolation for workspace_dir,
enabling shell injection via crafted path arguments. The fix replaces
os.system() with subprocess.run() using list arguments and cwd.
"""

import ast
import textwrap
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


class TestNoOsSystemInBenchmarkRunners:
    """Verify os.system() is not used in benchmark runner scripts."""

    @pytest.mark.parametrize(
        "script_name",
        ["run_dds_benchmark.py", "run_metr_benchmark.py"],
    )
    def test_no_os_system_calls(self, script_name: str):
        """Ensure benchmark scripts do not call os.system (shell injection risk).

        This test parses the AST looking for any call to os.system().
        It will FAIL if os.system() is reintroduced.
        """
        script_path = SCRIPTS_DIR / script_name
        assert script_path.exists(), f"{script_name} not found at {script_path}"

        source = script_path.read_text()
        tree = ast.parse(source, filename=script_name)

        os_system_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Match os.system(...)
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "system"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    os_system_calls.append(node.lineno)

        assert os_system_calls == [], (
            f"{script_name} contains os.system() calls at line(s) "
            f"{os_system_calls}. Use subprocess.run([...], cwd=...) instead "
            f"to prevent shell injection."
        )

    @pytest.mark.parametrize(
        "script_name",
        ["run_dds_benchmark.py", "run_metr_benchmark.py"],
    )
    def test_git_init_uses_subprocess_run(self, script_name: str):
        """Verify git init commands use subprocess.run with list args.

        This test confirms the safe pattern: subprocess.run(["git", ...], cwd=...)
        is used instead of shell string interpolation.
        """
        script_path = SCRIPTS_DIR / script_name
        source = script_path.read_text()

        # subprocess.run should be present
        assert "subprocess.run(" in source, (
            f"{script_name} should use subprocess.run() for git commands"
        )

        # The old unsafe pattern should not be present
        assert 'os.system(f"cd {workspace_dir}' not in source, (
            f"{script_name} still contains the unsafe os.system pattern"
        )

    @pytest.mark.parametrize(
        "script_name",
        ["run_dds_benchmark.py", "run_metr_benchmark.py"],
    )
    def test_no_shell_true_in_subprocess(self, script_name: str):
        """Ensure subprocess calls don't use shell=True (same vulnerability)."""
        script_path = SCRIPTS_DIR / script_name
        source = script_path.read_text()

        assert "shell=True" not in source, (
            f"{script_name} uses shell=True in subprocess call, "
            f"which has the same injection risk as os.system()"
        )
