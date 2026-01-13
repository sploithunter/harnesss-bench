#!/usr/bin/env python3
"""Verification script for Hello World task."""

import subprocess
import sys
from pathlib import Path


def main():
    # Find the hello.py file
    workspace = Path(__file__).parent
    hello_file = workspace / "src" / "hello.py"

    if not hello_file.exists():
        print("FAIL: src/hello.py not found")
        sys.exit(1)

    # Run the program
    try:
        result = subprocess.run(
            [sys.executable, str(hello_file)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: Program timed out")
        sys.exit(1)

    # Check output
    output = result.stdout.strip()
    expected = "Hello, World!"

    if output == expected:
        print("PASS: Output matches expected")
        sys.exit(0)
    else:
        print(f"FAIL: Expected '{expected}', got '{output}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
