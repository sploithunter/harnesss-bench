#!/usr/bin/env python3
"""Test script for Content Filtered Topic subscriber."""

import ast
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 60
EXPECTED_MIN_SAMPLES = 10  # At least this many matching samples


def check_syntax():
    """Check if subscriber.py has valid syntax."""
    try:
        with open("subscriber.py") as f:
            ast.parse(f.read())
        print("✓ Syntax OK")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        return False


def check_imports():
    """Check if subscriber.py imports are valid.
    
    Note: Some subscribers run at import time (no if __name__ guard),
    so we check import statements rather than actually importing.
    """
    try:
        with open("subscriber.py", "r") as f:
            code = f.read()
        
        # Check for common RTI imports
        has_dds = "rti.connextdds" in code or "rti.types" in code or "rti.idl" in code
        
        if has_dds:
            # Verify imports work by checking just the imports
            import_lines = [l for l in code.split('\n') if l.strip().startswith('import ') or l.strip().startswith('from ')]
            test_code = '\n'.join(import_lines)
            
            result = subprocess.run(
                [sys.executable, "-c", test_code],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                print("✓ Imports OK")
                return True
            else:
                print(f"✗ Import error: {result.stderr[:200]}")
                return False
        else:
            print("✗ Missing RTI DDS imports")
            return False
    except Exception as e:
        print(f"✗ Import check failed: {e}")
        return False


def check_cft_usage():
    """Check if ContentFilteredTopic is used."""
    with open("subscriber.py") as f:
        code = f.read()
    
    if "ContentFilteredTopic" in code:
        print("✓ ContentFilteredTopic used")
        return True
    else:
        print("✗ ContentFilteredTopic NOT found - using application filtering?")
        return False


def check_filter_expression():
    """Check if filter expression is correct."""
    with open("subscriber.py") as f:
        code = f.read()
    
    if "id > 50" in code and "value > 75" in code:
        print("✓ Filter expression looks correct")
        return True
    else:
        print("✗ Filter expression may be wrong (need: id > 50 AND value > 75.0)")
        return False


def run_functional_test_with_publisher(ref_publisher: Path) -> tuple[bool, int]:
    """Run subscriber with a specific publisher.
    
    Returns: (success, samples_received)
    
    Tries subscriber with args first, then without (models may not implement CLI args).
    """
    import json
    
    # Try different subscriber invocations
    sub_commands = [
        [sys.executable, "subscriber.py", "--count", "50", "--timeout", "30"],  # With args
        [sys.executable, "subscriber.py"],  # Without args (infinite loop, we'll kill it)
    ]
    
    for sub_cmd in sub_commands:
        # Start subscriber
        sub_proc = subprocess.Popen(
            sub_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        time.sleep(2)  # Let subscriber start
        
        # Start publisher (fewer samples for faster test)
        pub_proc = subprocess.Popen(
            [sys.executable, str(ref_publisher), "--samples", "200"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        try:
            # Wait for publisher to finish
            pub_proc.wait(timeout=15)
            time.sleep(2)  # Allow data delivery
            
            # Kill subscriber and capture output
            sub_proc.kill()
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            sub_proc.kill()
            pub_proc.kill()
            try:
                sub_stdout, _ = sub_proc.communicate(timeout=5)
            except:
                sub_stdout = ""
            continue
        except Exception:
            sub_proc.kill()
            pub_proc.kill()
            continue
        
        # Count received samples
        lines = [l for l in sub_stdout.strip().split("\n") if l.startswith("{")]
        received = len(lines)
        
        if received >= EXPECTED_MIN_SAMPLES:
            # Verify all samples match filter
            all_match = True
            for line in lines[:10]:  # Check first 10
                try:
                    data = json.loads(line)
                    if not (data["id"] > 50 and data["value"] > 75.0):
                        all_match = False
                        break
                except:
                    pass
            
            if all_match:
                return True, received
    
    return False, 0


def run_functional_test():
    """Run subscriber with the starter publisher.
    
    The starter publisher.py uses DynamicData and is provided to the model,
    so type compatibility should be straightforward.
    """
    script_dir = Path(__file__).parent
    
    # Use the starter publisher (same one the model sees)
    # This ensures type compatibility - the model can read the publisher to understand the type
    starter_publisher = script_dir / "publisher.py"
    
    if not starter_publisher.exists():
        # Fallback to starter directory if running from task dir
        starter_publisher = script_dir / "starter" / "publisher.py"
    
    if not starter_publisher.exists():
        print("✗ publisher.py not found")
        print("  Expected in workspace or starter/ directory")
        return False
    
    print(f"  Using publisher: {starter_publisher.name}")
    success, received = run_functional_test_with_publisher(starter_publisher)
    
    if success:
        print(f"✓ Received {received} matching samples")
        print("✓ All samples match filter criteria (id > 50 AND value > 75.0)")
        return True
    elif received > 0:
        print(f"✗ Received {received} samples but filter criteria not met")
        print("  Expected: id > 50 AND value > 75.0")
        return False
    else:
        print("✗ No samples received")
        print("  Check: type definition matches publisher.py, topic name is 'SensorReadings'")
        return False


def main():
    print("=" * 50)
    print("Content Filtered Topic Subscriber Test")
    print("=" * 50)
    
    if not Path("subscriber.py").exists():
        print("✗ subscriber.py not found")
        return 1
    
    tests = [
        ("Syntax", check_syntax),
        ("Imports", check_imports),
        ("CFT Usage", check_cft_usage),
        ("Filter Expression", check_filter_expression),
        ("Functional Test", run_functional_test),
    ]
    
    passed = 0
    for name, test in tests:
        print(f"\n--- {name} ---")
        if test():
            passed += 1
    
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("ALL TESTS PASSED")
    
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())

