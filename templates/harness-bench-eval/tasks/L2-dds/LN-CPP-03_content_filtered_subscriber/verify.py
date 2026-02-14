#!/usr/bin/env python3
"""
Verification script for LN-CPP-03: C++ ContentFilteredTopic Subscriber

Tests that the subscriber correctly uses ContentFilteredTopic to filter
sensor readings by sensor_id and value range.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from harness_bench.evaluation import check_dds_shmem


def verify(workspace: str = None) -> dict:
    """Verify the C++ ContentFilteredTopic subscriber implementation."""

    if workspace is None:
        workspace = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

    workspace = Path(workspace)
    results = {
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {}
    }
    checkpoints = []

    # Check DDS shared memory health (auto-cleans orphaned segments)
    shmem = check_dds_shmem()
    if shmem.get("cleanup"):
        results["details"]["dds_shmem_cleanup"] = shmem["cleanup"]
    if not shmem["ok"]:
        results["message"] = shmem["warning"]
        results["details"]["dds_shmem"] = shmem
        checkpoints.append({"name": "dds_shmem", "passed": False, "details": shmem})
        results["details"]["checkpoints"] = checkpoints
        return results

    # Check required files
    required_files = ["SensorReading.idl", "subscriber.cxx", "CMakeLists.txt"]
    missing = [f for f in required_files if not (workspace / f).exists()]

    checkpoints.append({
        "name": "files_exist",
        "passed": len(missing) == 0,
        "details": {"missing": missing} if missing else {}
    })

    if missing:
        results["message"] = f"Missing files: {missing}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Check IDL content
    idl_content = (workspace / "SensorReading.idl").read_text()
    idl_valid = all(x in idl_content for x in ["sensor_id", "value", "timestamp"])
    checkpoints.append({
        "name": "idl_valid",
        "passed": idl_valid,
        "details": {"content": idl_content[:200]}
    })

    if not idl_valid:
        results["message"] = "IDL file missing required fields"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run rtiddsgen
    nddshome = os.environ.get("NDDSHOME", "/opt/rti_connext_dds-7.5.0")
    rtiddsgen = Path(nddshome) / "bin" / "rtiddsgen"

    try:
        gen_result = subprocess.run(
            [str(rtiddsgen), "-language", "C++11", "-d", str(workspace),
             str(workspace / "SensorReading.idl"), "-replace"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=workspace
        )
        checkpoints.append({
            "name": "rtiddsgen_runs",
            "passed": gen_result.returncode == 0,
            "details": {
                "returncode": gen_result.returncode,
                "stderr": gen_result.stderr[:500] if gen_result.stderr else None
            }
        })
        if gen_result.returncode != 0:
            results["message"] = f"rtiddsgen failed: {gen_result.stderr[:200]}"
            results["details"]["checkpoints"] = checkpoints
            return results
    except Exception as e:
        results["message"] = f"rtiddsgen error: {e}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Build with cmake
    build_dir = workspace / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        cmake_result = subprocess.run(
            ["cmake", ".."],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=build_dir
        )
        checkpoints.append({
            "name": "cmake_runs",
            "passed": cmake_result.returncode == 0,
            "details": {
                "returncode": cmake_result.returncode,
                "stderr": cmake_result.stderr[:500] if cmake_result.stderr else None
            }
        })
        if cmake_result.returncode != 0:
            results["message"] = f"cmake failed: {cmake_result.stderr[:200]}"
            results["details"]["checkpoints"] = checkpoints
            return results
    except Exception as e:
        results["message"] = f"cmake error: {e}"
        results["details"]["checkpoints"] = checkpoints
        return results

    try:
        make_result = subprocess.run(
            ["make"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=build_dir
        )
        checkpoints.append({
            "name": "make_runs",
            "passed": make_result.returncode == 0,
            "details": {
                "returncode": make_result.returncode,
                "stderr": make_result.stderr[:500] if make_result.stderr else None
            }
        })
        if make_result.returncode != 0:
            results["message"] = f"make failed: {make_result.stderr[:200]}"
            results["details"]["checkpoints"] = checkpoints
            return results
    except Exception as e:
        results["message"] = f"make error: {e}"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Find subscriber executable
    subscriber_exe = None
    for name in ["subscriber", "cft_subscriber", "content_filtered_subscriber"]:
        exe_path = build_dir / name
        if exe_path.exists():
            subscriber_exe = exe_path
            break

    if not subscriber_exe:
        results["message"] = "No subscriber executable found in build/"
        results["details"]["checkpoints"] = checkpoints
        return results

    # Run interop test with Python publisher
    # The publisher sends 20 samples from 4 sensors with values designed to test filtering
    pub_code = '''
import rti.connextdds as dds
import rti.types as idl
import time
import sys
import argparse

@idl.struct(member_annotations={
    "sensor_id": [idl.bound(64)]
})
class SensorReading:
    sensor_id: str = ""
    value: float = 0.0
    timestamp: int = 0

parser = argparse.ArgumentParser()
parser.add_argument("--domain", type=int, default=0)
args = parser.parse_args()

participant = dds.DomainParticipant(args.domain)
topic = dds.Topic(participant, "SensorData", SensorReading)

writer_qos = dds.DataWriterQos()
writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
writer_qos.history.kind = dds.HistoryKind.KEEP_ALL

publisher = dds.Publisher(participant)
writer = dds.DataWriter(publisher, topic, writer_qos)

time.sleep(2)  # Wait for subscriber discovery

# Test data: 4 sensors, varying values
# sensor_B with values 25-75 should pass the filter
test_data = [
    # sensor_A - should NOT match (wrong sensor)
    ("sensor_A", 10.0),
    ("sensor_A", 50.0),
    ("sensor_A", 90.0),
    ("sensor_A", 30.0),
    ("sensor_A", 60.0),
    # sensor_B - some should match (25-75 range)
    ("sensor_B", 10.0),   # NO - below min
    ("sensor_B", 25.0),   # YES
    ("sensor_B", 50.0),   # YES
    ("sensor_B", 75.0),   # YES
    ("sensor_B", 90.0),   # NO - above max
    # sensor_C - should NOT match (wrong sensor)
    ("sensor_C", 25.0),
    ("sensor_C", 50.0),
    ("sensor_C", 75.0),
    ("sensor_C", 100.0),
    # sensor_D - should NOT match (wrong sensor)
    ("sensor_D", 0.0),
    ("sensor_D", 33.0),
    ("sensor_D", 66.0),
    ("sensor_D", 99.0),
    # More sensor_B samples in range
    ("sensor_B", 40.0),   # YES
    ("sensor_B", 60.0),   # YES
]

base_time = int(time.time() * 1000)
for i, (sensor, value) in enumerate(test_data):
    sample = SensorReading(
        sensor_id=sensor,
        value=value,
        timestamp=base_time + i * 100
    )
    writer.write(sample)
    time.sleep(0.1)

time.sleep(2)  # Allow samples to be received
print(f"Published {len(test_data)} samples")
'''

    try:
        env = os.environ.copy()

        # Find library path
        arch = os.environ.get("CONNEXTDDS_ARCH", "")
        lib_dir = Path(nddshome) / "lib" / arch
        if lib_dir.exists():
            lib_path = str(lib_dir)
        else:
            lib_path = None
            for d in (Path(nddshome) / "lib").iterdir():
                if d.is_dir():
                    lib_path = str(d)
                    break

        if lib_path:
            env["DYLD_LIBRARY_PATH"] = f"{lib_path}:{env.get('DYLD_LIBRARY_PATH', '')}"
            env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

        # Start C++ subscriber with filter parameters
        # Filter: sensor_id = "sensor_B", value in [25, 75]
        # Should receive 5 samples: 25.0, 50.0, 75.0, 40.0, 60.0
        sub_proc = subprocess.Popen(
            [str(subscriber_exe), "--sensor", "sensor_B",
             "--min-value", "25", "--max-value", "75",
             "--count", "5", "--timeout", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=workspace
        )

        time.sleep(2)  # Let subscriber start

        # Run Python publisher
        pub_proc = subprocess.Popen(
            [sys.executable, "-c", pub_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace
        )

        try:
            pub_stdout, pub_stderr = pub_proc.communicate(timeout=30)
            sub_stdout, sub_stderr = sub_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pub_proc.kill()
            sub_proc.kill()
            sub_stdout, sub_stderr = sub_proc.communicate()
            pub_stdout = ""

        # Parse received samples
        lines = [l for l in sub_stdout.strip().split("\n") if l.strip()]
        received_samples = []
        for line in lines:
            try:
                data = json.loads(line)
                if "sensor_id" in data and "value" in data:
                    received_samples.append(data)
            except json.JSONDecodeError:
                pass

        # Validate filtering worked correctly
        # All received samples should match: sensor_id="sensor_B" AND 25 <= value <= 75
        filter_errors = []
        for sample in received_samples:
            if sample["sensor_id"] != "sensor_B":
                filter_errors.append(f"Wrong sensor: {sample['sensor_id']}")
            if sample["value"] < 25 or sample["value"] > 75:
                filter_errors.append(f"Value out of range: {sample['value']}")

        # Expected matching samples from test data: 25.0, 50.0, 75.0, 40.0, 60.0 (5 total)
        expected_count = 5
        filter_working = len(filter_errors) == 0 and len(received_samples) >= 3

        checkpoints.append({
            "name": "content_filter_test",
            "passed": filter_working,
            "details": {
                "received": len(received_samples),
                "expected_min": 3,
                "expected_max": expected_count,
                "filter_errors": filter_errors[:5] if filter_errors else [],
                "samples": received_samples[:5],
                "stdout": sub_stdout[:500] if sub_stdout else None,
                "stderr": sub_stderr[:500] if sub_stderr else None
            }
        })

        # Pass/fail determination
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["files_exist", "idl_valid", "rtiddsgen_runs",
                                   "cmake_runs", "make_runs", "content_filter_test"]
        )

        results["success"] = all_critical_passed
        results["score"] = 1.0 if results["success"] else 0.0

        if filter_errors:
            results["message"] = f"ContentFilteredTopic not working: {filter_errors[0]}"
        elif len(received_samples) < 3:
            results["message"] = f"Only received {len(received_samples)} samples, expected at least 3"
        else:
            results["message"] = f"ContentFilteredTopic working: {len(received_samples)} filtered samples received"

        results["details"]["samples_received"] = len(received_samples)
        results["details"]["filter_errors"] = len(filter_errors)
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
