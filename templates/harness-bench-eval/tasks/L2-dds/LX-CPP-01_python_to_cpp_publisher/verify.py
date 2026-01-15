#!/usr/bin/env python3
"""Verification script for LX-CPP-01_python_to_cpp_publisher.

Model translates a Python DDS publisher to C++. The workspace contains:
- publisher.py (original Python - for reference)
- subscriber.py (Python subscriber to test interop)

Model creates:
- publisher.cxx (translated C++ publisher)
- HelloWorld.idl (IDL type definition)
- CMakeLists.txt (build configuration)

Test workflow:
1. Check required files exist
2. Run rtiddsgen for C++11
3. Build with cmake/make
4. Run interop test: C++ publisher → Python subscriber (from workspace)

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def verify() -> dict:
    """Run verification and return results."""
    workspace = Path.cwd()
    eval_dir = Path(os.environ.get("EVAL_DIR", Path(__file__).parent))

    results = {
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {},
    }

    checkpoints = []

    # Check required files created by model
    required_files = ["publisher.cxx", "CMakeLists.txt"]
    missing = [f for f in required_files if not (workspace / f).exists()]

    # IDL can be optional if using inline type definition in C++
    idl_file = workspace / "HelloWorld.idl"
    has_idl = idl_file.exists()

    if missing:
        results["message"] = f"Missing files: {missing}"
        checkpoints.append({
            "name": "files_exist",
            "passed": False,
            "details": {"missing": missing, "has_idl": has_idl}
        })
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "files_exist", "passed": True, "details": {"has_idl": has_idl}})

    # Check Python subscriber exists (provided in workspace)
    subscriber_file = workspace / "subscriber.py"
    if not subscriber_file.exists():
        results["message"] = "subscriber.py not found in workspace"
        checkpoints.append({"name": "subscriber_exists", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "subscriber_exists", "passed": True})

    # Check NDDSHOME
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        results["message"] = "NDDSHOME not set - cannot build C++ code"
        checkpoints.append({"name": "nddshome_set", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "nddshome_set", "passed": True})

    # If IDL exists, run rtiddsgen
    if has_idl:
        # Validate IDL content
        with open(idl_file) as f:
            idl_content = f.read()

        idl_valid = (
            "struct HelloWorld" in idl_content
            and "message" in idl_content
            and "count" in idl_content
        )
        checkpoints.append({
            "name": "idl_valid",
            "passed": idl_valid,
            "details": {"has_struct": "struct HelloWorld" in idl_content}
        })

        if not idl_valid:
            results["message"] = "HelloWorld.idl missing required fields"
            results["details"]["checkpoints"] = checkpoints
            return results

        # Run rtiddsgen for C++11
        rtiddsgen = Path(nddshome) / "bin" / "rtiddsgen"
        if not rtiddsgen.exists():
            results["message"] = f"rtiddsgen not found at {rtiddsgen}"
            checkpoints.append({"name": "rtiddsgen_exists", "passed": False})
            results["details"]["checkpoints"] = checkpoints
            return results

        proc = subprocess.run(
            [str(rtiddsgen), "-language", "C++11", "-d", str(workspace), "-replace", str(idl_file)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=workspace,
        )

        generated_cxx = workspace / "HelloWorld.cxx"
        rtiddsgen_ok = proc.returncode == 0 and generated_cxx.exists()
        checkpoints.append({
            "name": "rtiddsgen_runs",
            "passed": rtiddsgen_ok,
            "details": {"stderr": proc.stderr[:500] if proc.stderr else None}
        })

        if not rtiddsgen_ok:
            results["message"] = f"rtiddsgen failed: {proc.stderr}"
            results["details"]["checkpoints"] = checkpoints
            return results

    # Build with cmake
    build_dir = workspace / "build"
    build_dir.mkdir(exist_ok=True)

    # Run cmake
    proc = subprocess.run(
        ["cmake", "..", f"-DCONNEXTDDS_DIR={nddshome}"],
        cwd=str(build_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )

    cmake_ok = proc.returncode == 0
    checkpoints.append({
        "name": "cmake_runs",
        "passed": cmake_ok,
        "details": {"stderr": proc.stderr[-500:] if proc.stderr else None}
    })

    if not cmake_ok:
        results["message"] = f"cmake failed: {proc.stderr[-500:]}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run make
    proc = subprocess.run(
        ["make", "-j4"],
        cwd=str(build_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )

    publisher_exe = build_dir / "publisher"
    make_ok = proc.returncode == 0 and publisher_exe.exists()
    checkpoints.append({
        "name": "make_runs",
        "passed": make_ok,
        "details": {"stderr": proc.stderr[-500:] if proc.stderr else None}
    })

    if not make_ok:
        results["message"] = f"make failed: {proc.stderr[-500:]}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run interop test: C++ publisher with workspace's Python subscriber
    try:
        # Start Python subscriber from workspace
        sub_proc = subprocess.Popen(
            [sys.executable, str(subscriber_file), "--count", "10", "--timeout", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        time.sleep(2)

        # Set up library path for C++ executable
        env = os.environ.copy()
        arch = os.environ.get("CONNEXTDDS_ARCH", "")
        lib_path = None

        if arch and (Path(nddshome) / "lib" / arch).exists():
            lib_path = str(Path(nddshome) / "lib" / arch)
        else:
            # Find directory containing shared libraries
            for lib_dir in Path(nddshome).glob("lib/*"):
                if lib_dir.is_dir():
                    if list(lib_dir.glob("*.dylib")) or list(lib_dir.glob("*.so")):
                        lib_path = str(lib_dir)
                        break

        if lib_path:
            env["DYLD_LIBRARY_PATH"] = f"{lib_path}:{env.get('DYLD_LIBRARY_PATH', '')}"
            env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

        # Run C++ publisher
        pub_proc = subprocess.Popen(
            [str(publisher_exe), "--count", "10"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=workspace,
        )

        try:
            pub_stdout, pub_stderr = pub_proc.communicate(timeout=30)
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pub_proc.kill()
            sub_proc.kill()
            sub_stdout, _ = sub_proc.communicate()
            pub_stdout = ""

        # Count received samples
        lines = [l for l in sub_stdout.strip().split("\n") if l.strip().startswith("{")]
        samples_received = len(lines)

        checkpoints.append({
            "name": "interop_test",
            "passed": samples_received >= 10,
            "details": {"received": samples_received, "expected": 10}
        })

        # Pass/fail
        critical_checkpoints = ["files_exist", "cmake_runs", "make_runs", "interop_test"]
        if has_idl:
            critical_checkpoints.extend(["idl_valid", "rtiddsgen_runs"])

        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in critical_checkpoints
        )

        results["success"] = all_critical_passed
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"Python to C++ translation interop test: {samples_received}/10 samples received"
        results["details"]["samples_received"] = samples_received
        results["details"]["checkpoints"] = checkpoints

    except subprocess.TimeoutExpired:
        results["message"] = "Interop test timed out"
        results["score"] = 0.0
    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
