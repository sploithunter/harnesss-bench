# Implementing a New Harness

This guide explains how to add support for a new AI coding assistant to harness-bench.

## Overview

A harness bridge adapts an AI coding assistant to work with the harness-bench protocol. Bridges handle:
1. Workspace setup and initialization
2. Invoking the harness CLI or API
3. Committing changes following the protocol
4. Tracking progress and signaling completion

## Quick Start

For most use cases, extend `RalphLoopBase` from `harness_bench.harnesses.ralph_base`:

```python
from pathlib import Path
from harness_bench.harnesses.ralph_base import RalphLoopBase
from harness_bench.exceptions import EnvironmentError

class MyHarnessRalphLoopBridge(RalphLoopBase):
    """Ralph-style loop bridge for MyHarness."""

    harness_id = "my-harness"
    harness_vendor = "my-company"
    harness_version = "1.0.0"

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Execute the harness CLI with the given prompt."""
        # Build and run your CLI command
        cmd = ["my-harness", "--prompt", prompt]
        # ... subprocess execution logic
        return True, "completed"  # or False, "reason"

    def _get_env(self) -> dict[str, str]:
        """Get environment variables with required API keys."""
        import os
        env = os.environ.copy()
        if "MY_API_KEY" not in env:
            raise EnvironmentError("MY_API_KEY not set")
        return env
```

## Key Concepts

### 1. RalphLoopBase vs HarnessBridge

**HarnessBridge** (`harness_bench.core.bridge`) is the low-level base class that handles:
- Git branch creation
- Manifest management
- Commit formatting
- Event logging

**RalphLoopBase** (`harness_bench.harnesses.ralph_base`) extends HarnessBridge with:
- Iteration loop with timeout management
- Stagnation detection (circuit breaker)
- Verification script integration
- Progress tracking in files
- Consistent logging

For benchmark tasks, **use RalphLoopBase** unless you have specific reasons not to.

### 2. Required Methods

When extending `RalphLoopBase`, you must implement:

#### `_run_harness_command(prompt, timeout)`

Execute your harness CLI and return results.

```python
def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
    """
    Args:
        prompt: The task prompt to send to the harness
        timeout: Maximum time in seconds for this iteration

    Returns:
        Tuple of (success: bool, reason: str)
        - success: True if command completed successfully
        - reason: Short description ("completed", "timeout", "exit_code=1", etc.)
    """
```

#### `_get_env()`

Return environment variables for subprocess execution.

```python
def _get_env(self) -> dict[str, str]:
    """
    Returns:
        Environment dictionary with required API keys

    Raises:
        EnvironmentError: If required keys are missing
    """
```

### 3. Optional Overrides

You can override these for customization:

- `log_filename` - Property for the log file name
- `_init_state_files()` - Customize state file initialization
- `_build_base_prompt(task_prompt)` - Customize prompt building
- `execute_task(task_prompt)` - Override the entire execution loop

## Best Practices

### Process Management

Use process groups for reliable timeout handling:

```python
import os
import signal
import subprocess

proc = subprocess.Popen(
    cmd,
    cwd=self.workspace,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=self._get_env(),
    preexec_fn=os.setsid if os.name != 'nt' else None,
)

try:
    stdout, stderr = proc.communicate(timeout=timeout)
except subprocess.TimeoutExpired:
    if os.name != 'nt':
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    else:
        proc.kill()
    proc.wait()
    return False, "timeout"
```

### Error Handling

Use custom exceptions from `harness_bench.exceptions`:

```python
from harness_bench.exceptions import (
    EnvironmentError,  # Missing API keys
    BridgeExecutionError,  # Command failures
    TimeoutError,  # Timeouts
)
```

### Logging

Use the `_log()` method for consistent logging:

```python
self._log("Starting harness execution...")
self._log("Command failed", level="ERROR")
self._log("Verification passed!", level="SUCCESS")
```

### Cost Tracking

Track costs if your harness provides usage information:

```python
# Add to total cost
self.total_cost_usd += iteration_cost
self._log(f"Iteration cost: ${iteration_cost:.4f}, Total: ${self.total_cost_usd:.4f}")
```

## Testing Your Harness

### 1. Unit Tests

Create tests in `tests/unit/test_my_harness.py`:

```python
import pytest
from pathlib import Path
from harness_bench.harnesses.my_harness import MyHarnessRalphLoopBridge

def test_harness_id():
    """Test harness identifier."""
    assert MyHarnessRalphLoopBridge.harness_id == "my-harness"

def test_get_env_requires_key(monkeypatch):
    """Test API key requirement."""
    monkeypatch.delenv("MY_API_KEY", raising=False)
    bridge = MyHarnessRalphLoopBridge(workspace=Path("/tmp"))
    with pytest.raises(EnvironmentError):
        bridge._get_env()
```

### 2. Integration Tests

Test with a real task:

```bash
python scripts/run_dds_benchmark.py \
    --harness my-harness \
    --model my-model \
    --tasks L1-PY-01 \
    --timeout 300 \
    --dev-mode
```

## Registering Your Harness

Add your harness to `src/harness_bench/harnesses/__init__.py`:

```python
from .my_harness import MyHarnessRalphLoopBridge

__all__ = [
    # ... existing exports
    "MyHarnessRalphLoopBridge",
]
```

## Example: Minimal Implementation

Here's a complete minimal example:

```python
"""Minimal harness bridge example."""

import os
import signal
import subprocess
from pathlib import Path

from harness_bench.harnesses.ralph_base import RalphLoopBase
from harness_bench.exceptions import EnvironmentError


class MinimalRalphLoopBridge(RalphLoopBase):
    """Minimal Ralph-style loop bridge."""

    harness_id = "minimal"
    harness_vendor = "example"
    harness_version = "1.0.0"

    def _run_harness_command(self, prompt: str, timeout: float) -> tuple[bool, str]:
        """Run minimal CLI."""
        cmd = ["echo", prompt]  # Replace with real CLI

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                if proc.returncode == 0:
                    return True, "completed"
                return False, f"exit_code={proc.returncode}"
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
                proc.wait()
                return False, "timeout"

        except FileNotFoundError:
            self._log("CLI not found", "ERROR")
            return False, "not_found"
        except Exception as e:
            self._log(f"Error: {e}", "ERROR")
            return False, f"error: {e}"

    def _get_env(self) -> dict[str, str]:
        """Get environment."""
        env = os.environ.copy()
        # Uncomment to require an API key:
        # if "MINIMAL_API_KEY" not in env:
        #     raise EnvironmentError("MINIMAL_API_KEY not set")
        return env
```

## Getting Help

- See existing implementations in `src/harness_bench/harnesses/`
- Review `RalphLoopBase` in `ralph_base.py` for available hooks
- Check [HARNESS_STATUS.md](HARNESS_STATUS.md) for known issues with other harnesses
