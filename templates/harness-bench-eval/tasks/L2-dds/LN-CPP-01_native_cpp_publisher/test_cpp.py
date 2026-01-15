#!/usr/bin/env python3
"""Test script for Native C++ Publisher task.

Handles the full workflow:
1. Check required files
2. Build with cmake
3. Run interoperability test with Python subscriber
"""

import os
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 120


def check_files():
    """Check required files exist."""
    required = ["HelloWorld.idl", "publisher.cxx", "CMakeLists.txt"]
    missing = [f for f in required if not Path(f).exists()]
    
    if missing:
        print(f"✗ Missing files: {missing}")
        return False
    
    print("✓ All required files present")
    return True


def check_idl():
    """Check IDL content."""
    with open("HelloWorld.idl") as f:
        content = f.read()
    
    if "struct HelloWorld" in content and "message" in content and "count" in content:
        print("✓ HelloWorld.idl looks valid")
        return True
    
    print("✗ HelloWorld.idl missing required fields")
    return False


def build_cpp():
    """Build the C++ publisher with cmake."""
    build_dir = Path("build")
    
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        print("✗ NDDSHOME not set")
        return False
    
    # Run rtiddsgen first to generate C++ types
    rtiddsgen = Path(nddshome) / "bin" / "rtiddsgen"
    if not rtiddsgen.exists():
        print(f"✗ rtiddsgen not found at {rtiddsgen}")
        return False
    
    print("Running rtiddsgen...")
    result = subprocess.run(
        [str(rtiddsgen), "-language", "C++11", "-d", ".", "-replace", "HelloWorld.idl"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    if result.returncode != 0:
        print(f"✗ rtiddsgen failed: {result.stderr}")
        return False
    
    if not Path("HelloWorld.cxx").exists():
        print("✗ rtiddsgen didn't generate HelloWorld.cxx")
        return False
    
    print("✓ rtiddsgen succeeded")
    
    # Create build directory
    build_dir.mkdir(exist_ok=True)
    
    # Run cmake
    print("Running cmake...")
    result = subprocess.run(
        ["cmake", "..", f"-DCONNEXTDDS_DIR={nddshome}"],
        cwd=str(build_dir),
        capture_output=True,
        text=True,
        timeout=60
    )
    
    if result.returncode != 0:
        print(f"✗ cmake failed:")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        return False
    
    print("✓ cmake succeeded")
    
    # Run make
    print("Running make...")
    result = subprocess.run(
        ["make", "-j4"],
        cwd=str(build_dir),
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
        print(f"✗ make failed:")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        return False
    
    if not (build_dir / "publisher").exists():
        print("✗ publisher executable not created")
        return False
    
    print("✓ Build succeeded")
    return True


def run_interop_test():
    """Run C++ publisher with Python subscriber."""
    nddshome = os.environ.get("NDDSHOME")
    ref_subscriber = Path("reference/subscriber.py")
    if not ref_subscriber.exists():
        # Create a simple Python subscriber inline
        sub_code = '''
import sys, json, time, argparse, signal
import rti.connextdds as dds

running = True
def handler(s, f):
    global running
    running = False
signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=10)
parser.add_argument("--timeout", type=float, default=30)
args = parser.parse_args()

t = dds.StructType("HelloWorld")
t.add_member(dds.Member("message", dds.StringType(256)))
t.add_member(dds.Member("count", dds.Int32Type()))

p = dds.DomainParticipant(0)
topic = dds.DynamicData.Topic(p, "HelloWorld", t)

qos = dds.DataReaderQos()
qos.reliability.kind = dds.ReliabilityKind.RELIABLE
qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
reader = dds.DynamicData.DataReader(dds.Subscriber(p), topic, qos)

ws = dds.WaitSet()
cond = dds.ReadCondition(reader, dds.DataState.any_data)
ws.attach_condition(cond)

received = 0
start = time.time()
while running and received < args.count and (time.time() - start) < args.timeout:
    active = ws.wait(dds.Duration.from_seconds(1.0))
    if cond in active:
        for s in reader.take():
            if s.info.valid:
                print(json.dumps({"message": s.data["message"], "count": s.data["count"]}), flush=True)
                received += 1
'''
        result = subprocess.Popen(
            [sys.executable, "-c", sub_code, "--count", "10", "--timeout", "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    else:
        result = subprocess.Popen(
            [sys.executable, str(ref_subscriber), "--count", "10", "--timeout", "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    
    sub_proc = result
    
    time.sleep(2)
    
    # Run C++ publisher with library path set
    env = os.environ.copy()
    # Find the architecture-specific library directory (contains .dylib or .so files)
    lib_path = None
    arch = os.environ.get("CONNEXTDDS_ARCH", "")
    if arch and (Path(nddshome) / "lib" / arch).exists():
        lib_path = str(Path(nddshome) / "lib" / arch)
    else:
        # Look for directory containing shared libraries
        for lib_dir in Path(nddshome).glob("lib/*"):
            if lib_dir.is_dir() and list(lib_dir.glob("*.dylib")) or list(lib_dir.glob("*.so")):
                lib_path = str(lib_dir)
                break
    
    if lib_path:
        if "DYLD_LIBRARY_PATH" in env:
            env["DYLD_LIBRARY_PATH"] = f"{lib_path}:{env['DYLD_LIBRARY_PATH']}"
        else:
            env["DYLD_LIBRARY_PATH"] = lib_path
        if "LD_LIBRARY_PATH" in env:
            env["LD_LIBRARY_PATH"] = f"{lib_path}:{env['LD_LIBRARY_PATH']}"
        else:
            env["LD_LIBRARY_PATH"] = lib_path
    
    pub_proc = subprocess.Popen(
        ["./build/publisher", "--count", "10"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env
    )
    
    try:
        pub_stdout, pub_stderr = pub_proc.communicate(timeout=30)
        sub_stdout, sub_stderr = sub_proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        pub_proc.kill()
        sub_proc.kill()
        print("✗ Timeout during interop test")
        return False
    
    # Count received samples
    lines = [l for l in sub_stdout.strip().split("\n") if l.strip()]
    received = len(lines)
    
    print(f"Received {received}/10 samples")
    
    if received >= 10:
        print("✓ Interoperability test passed")
        return True
    else:
        print("✗ Not enough samples received")
        return False


def main():
    print("=" * 50)
    print("Native C++ Publisher Test")
    print("=" * 50)
    print()
    
    tests = [
        ("Files Present", check_files),
        ("IDL Valid", check_idl),
        ("Build C++", build_cpp),
        ("Interop Test", run_interop_test),
    ]
    
    passed = 0
    for name, test in tests:
        print(f"\n--- {name} ---")
        try:
            if test():
                passed += 1
            else:
                # Stop on first failure for build dependencies
                if name in ["Files Present", "IDL Valid", "Build C++"]:
                    break
        except Exception as e:
            print(f"✗ Error: {e}")
            break
    
    print()
    print("=" * 50)
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("ALL TESTS PASSED")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

