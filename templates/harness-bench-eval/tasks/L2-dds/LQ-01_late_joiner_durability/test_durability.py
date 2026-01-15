#!/usr/bin/env python3
"""Test harness for Late Joiner Durability challenge.

Runs publisher and subscriber with RANDOM startup order.
Tests that all samples are received regardless of which starts first.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXPECTED_SAMPLES = 10
NUM_RUNS = 5
TIMEOUT = 15  # Shorter timeout per run


def run_single_test(run_num: int, pub_first: bool):
    """Run a single test with specified startup order."""
    
    script_dir = Path(__file__).parent
    publisher = script_dir / "publisher.py"
    subscriber = script_dir / "subscriber.py"
    
    # Verify files exist
    if not publisher.exists():
        print(f"  ❌ publisher.py not found")
        return False
    if not subscriber.exists():
        print(f"  ❌ subscriber.py not found")
        return False
    
    order = "Publisher first" if pub_first else "Subscriber first"
    delay = random.uniform(0.5, 2.0)  # Random delay between 0.5-2 seconds
    
    print(f"  Run {run_num}: {order} (delay: {delay:.1f}s)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.jsonl"
        
        if pub_first:
            # Publisher starts first
            pub_proc = subprocess.Popen(
                [sys.executable, str(publisher), "--count", str(EXPECTED_SAMPLES)],
                stderr=subprocess.PIPE,
            )
            
            # Delay before starting subscriber (simulating late join)
            time.sleep(delay)
            
            sub_proc = subprocess.Popen(
                [sys.executable, str(subscriber), 
                 "--count", str(EXPECTED_SAMPLES),
                 "--timeout", str(TIMEOUT)],
                stdout=open(output_file, "w"),
                stderr=subprocess.PIPE,
            )
        else:
            # Subscriber starts first
            sub_proc = subprocess.Popen(
                [sys.executable, str(subscriber),
                 "--count", str(EXPECTED_SAMPLES),
                 "--timeout", str(TIMEOUT)],
                stdout=open(output_file, "w"),
                stderr=subprocess.PIPE,
            )
            
            # Delay before starting publisher
            time.sleep(delay)
            
            pub_proc = subprocess.Popen(
                [sys.executable, str(publisher), "--count", str(EXPECTED_SAMPLES)],
                stderr=subprocess.PIPE,
            )
        
        # Wait for both to finish
        try:
            pub_proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            pub_proc.kill()
        
        try:
            sub_proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            sub_proc.kill()
        
        # Check results
        if not output_file.exists():
            print(f"    ❌ No output file")
            return False
        
        with open(output_file) as f:
            lines = f.readlines()
        
        samples = []
        for line in lines:
            try:
                samples.append(json.loads(line))
            except:
                pass
        
        if len(samples) >= EXPECTED_SAMPLES:
            print(f"    ✓ Received {len(samples)}/{EXPECTED_SAMPLES}")
            return True
        else:
            print(f"    ❌ Received {len(samples)}/{EXPECTED_SAMPLES}")
            return False


def main():
    print("=" * 60)
    print("Late Joiner Durability Test")
    print("=" * 60)
    print()
    print(f"Running {NUM_RUNS} tests with random startup order...")
    print()
    
    passed = 0
    
    for i in range(NUM_RUNS):
        # Randomly choose startup order
        pub_first = random.choice([True, False])
        
        if run_single_test(i + 1, pub_first):
            passed += 1
    
    print()
    print("=" * 60)
    if passed == NUM_RUNS:
        print(f"ALL TESTS PASSED ({passed}/{NUM_RUNS})")
        print("=" * 60)
        return 0
    else:
        print(f"TESTS FAILED ({passed}/{NUM_RUNS} passed)")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())

