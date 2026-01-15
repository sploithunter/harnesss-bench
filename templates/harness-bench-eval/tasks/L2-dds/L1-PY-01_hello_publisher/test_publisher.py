#!/usr/bin/env python3
"""Test script for the Hello World Publisher.

Aider can run this to verify the publisher works before final verification.
Returns exit code 0 on success, non-zero on failure.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path


def test_publisher():
    """Test the publisher by running it with a reference subscriber."""
    publisher_file = Path("publisher.py")
    
    if not publisher_file.exists():
        print("❌ FAIL: publisher.py not found")
        return 1
    
    # Test 1: Check syntax
    print("Test 1: Checking syntax...")
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(publisher_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"❌ FAIL: Syntax error")
        print(result.stderr)
        return 1
    print("  ✓ Syntax OK")
    
    # Test 2: Check imports
    print("\nTest 2: Checking imports...")
    result = subprocess.run(
        [sys.executable, "-c", "import publisher"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        print(f"❌ FAIL: Import error")
        print(result.stderr)
        return 1
    print("  ✓ Imports OK")
    
    # Test 3: Quick run test (just startup, not full publish)
    print("\nTest 3: Quick startup test...")
    try:
        result = subprocess.run(
            [sys.executable, str(publisher_file)],
            capture_output=True,
            text=True,
            timeout=8,  # Should start but timeout before finishing
        )
        # If it exits cleanly in <8s, that's fine (fast publish)
        if result.returncode == 0:
            print("  ✓ Publisher ran successfully")
        else:
            print(f"  ⚠ Publisher exited with code {result.returncode}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        # Expected - means it started and is publishing
        print("  ✓ Publisher started (timeout expected)")
    
    # Test 4: Full run with sample capture (tries both type systems)
    print("\nTest 4: Full publish test with sample capture...")
    
    script_dir = Path(__file__).parent
    ref_dir = script_dir / "reference"
    
    # Try both subscriber types - model may use either @idl.struct or DynamicData
    subscribers = [
        (ref_dir / "subscriber_idl.py", "IDL (@idl.struct)"),
        (ref_dir / "subscriber_dynamic.py", "DynamicData"),
        (ref_dir / "subscriber.py", "default"),
    ]
    
    for sub_path, sub_name in subscribers:
        if not sub_path.exists():
            continue
            
        output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        output_file.close()
        
        try:
            # Start subscriber
            sub_proc = subprocess.Popen(
                [sys.executable, str(sub_path), 
                 "--domain", "85", "--count", "10", "--timeout", "20",
                 "--output", output_file.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            time.sleep(2)  # Wait for subscriber to start
            
            # Run publisher
            pub_result = subprocess.run(
                [sys.executable, str(publisher_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Wait for subscriber
            try:
                sub_stdout, sub_stderr = sub_proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                sub_proc.kill()
                continue
            
            # Check results
            if pub_result.returncode != 0:
                continue  # Try next subscriber type
            
            # Count samples
            with open(output_file.name) as f:
                samples = [line for line in f if line.strip()]
            
            if len(samples) >= 10:
                print(f"  ✓ Received {len(samples)} samples (using {sub_name} subscriber)")
                print("\n✅ ALL TESTS PASSED")
                return 0
            elif len(samples) > 0:
                print(f"  Partial: {len(samples)} samples with {sub_name}")
                
        except Exception:
            pass
        finally:
            Path(output_file.name).unlink(missing_ok=True)
    
    print("❌ FAIL: No samples received with any subscriber type")
    print("         (Tried both @idl.struct and DynamicData type systems)")
    return 1


if __name__ == "__main__":
    sys.exit(test_publisher())


