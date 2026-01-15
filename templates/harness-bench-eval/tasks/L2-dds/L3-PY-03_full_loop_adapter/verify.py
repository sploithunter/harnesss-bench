#!/usr/bin/env python3
"""Verification script for L3-PY-03_full_loop_adapter.

Model creates inbound_adapter.py (Binary → DDS) and outbound_adapter.py (DDS → Binary).
Test: Binary → inbound → DDS → outbound → Binary. Compare input/output.

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness_bench.evaluation import preflight_check, check_syntax


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

    # Check for required files
    inbound_file = workspace / "inbound_adapter.py"
    outbound_file = workspace / "outbound_adapter.py"

    if not inbound_file.exists():
        results["message"] = "inbound_adapter.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    if not outbound_file.exists():
        results["message"] = "outbound_adapter.py not found"
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "files_exist", "passed": True})

    # Check syntax
    for name, filepath in [("inbound", inbound_file), ("outbound", outbound_file)]:
        passed, error = check_syntax(filepath)
        if not passed:
            results["message"] = f"Syntax error in {name}_adapter.py: {error}"
            checkpoints.append({"name": f"{name}_syntax", "passed": False, "details": {"error": error}})
            results["details"]["checkpoints"] = checkpoints
            return results
        checkpoints.append({"name": f"{name}_syntax", "passed": True})

    # Copy protocol.py to workspace if not present
    protocol_src = eval_dir / "reference" / "protocol.py"
    protocol_dst = workspace / "protocol.py"
    if not protocol_dst.exists() and protocol_src.exists():
        shutil.copy(protocol_src, protocol_dst)

    # Import protocol
    sys.path.insert(0, str(eval_dir / "reference"))
    from protocol import generate_test_messages, encode_message, decode_message

    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.bin"
        output_file = Path(tmpdir) / "output.bin"

        # Generate test messages
        test_count = 10
        messages = generate_test_messages(test_count)

        with open(input_file, "wb") as f:
            for msg in messages:
                f.write(encode_message(msg))

        # === PREFLIGHT CHECKS ===
        # Run each adapter briefly to catch runtime errors before full test
        passed, error = preflight_check(
            inbound_file,
            ["--input", str(input_file), "--domain", "0"],
            cwd=workspace,
        )
        if not passed:
            checkpoints.append({"name": "inbound_preflight", "passed": False, "details": {"stderr": error}})
            results["message"] = "inbound_adapter.py crashed during preflight"
            results["details"]["checkpoints"] = checkpoints
            return results
        checkpoints.append({"name": "inbound_preflight", "passed": True})

        preflight_output = Path(tmpdir) / "preflight.bin"
        passed, error = preflight_check(
            outbound_file,
            ["--output", str(preflight_output), "--domain", "0", "--count", "1", "--timeout", "2"],
            cwd=workspace,
        )
        if not passed:
            checkpoints.append({"name": "outbound_preflight", "passed": False, "details": {"stderr": error}})
            results["message"] = "outbound_adapter.py crashed during preflight"
            results["details"]["checkpoints"] = checkpoints
            return results
        checkpoints.append({"name": "outbound_preflight", "passed": True})

        # === FULL TEST ===
        outbound_proc = None
        inbound_proc = None

        try:
            # Start outbound (subscriber)
            outbound_proc = subprocess.Popen(
                [sys.executable, str(outbound_file),
                 "--output", str(output_file),
                 "--domain", "0",
                 "--count", str(test_count),
                 "--timeout", "15"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workspace,
            )

            # Start inbound (publisher)
            inbound_proc = subprocess.Popen(
                [sys.executable, str(inbound_file),
                 "--input", str(input_file),
                 "--domain", "0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workspace,
            )

            # Wait for inbound to finish
            inbound_stdout, inbound_stderr = inbound_proc.communicate(timeout=15)
            checkpoints.append({
                "name": "inbound_runs",
                "passed": inbound_proc.returncode == 0,
                "details": {
                    "returncode": inbound_proc.returncode,
                    "stdout": inbound_stdout.decode()[:500] if inbound_stdout else None,
                    "stderr": inbound_stderr.decode()[:500] if inbound_stderr else None
                }
            })

            # Wait for outbound to finish or timeout
            try:
                outbound_stdout, outbound_stderr = outbound_proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                outbound_proc.terminate()
                outbound_stdout, outbound_stderr = outbound_proc.communicate(timeout=5)

            outbound_stderr_str = outbound_stderr.decode() if outbound_stderr else ""
            checkpoints.append({
                "name": "outbound_runs",
                "passed": True,
                "details": {
                    "returncode": outbound_proc.returncode,
                    "stdout": outbound_stdout.decode()[:500] if outbound_stdout else None,
                    "stderr": outbound_stderr_str[:500] if outbound_stderr_str else None
                }
            })

            # Check output
            checkpoints.append({
                "name": "output_created",
                "passed": output_file.exists() and output_file.stat().st_size > 0
            })

            # Decode received messages
            messages_received = []
            if output_file.exists() and output_file.stat().st_size > 0:
                with open(output_file, "rb") as f:
                    data = f.read()
                while data:
                    msg, data = decode_message(data)
                    messages_received.append(msg)

            received_count = len(messages_received)
            checkpoints.append({
                "name": "message_count",
                "passed": received_count >= 1,
                "details": {"received": received_count, "expected": test_count}
            })

            # Verify data integrity
            def get_id(msg):
                return msg.seq if hasattr(msg, 'seq') else msg.id

            sent_by_id = {get_id(m): m for m in messages}
            matches = 0
            for out in messages_received:
                out_id = get_id(out)
                if out_id in sent_by_id:
                    inp = sent_by_id[out_id]
                    if type(inp) == type(out):
                        inp_dict = inp.to_dict()
                        out_dict = out.to_dict()
                        if inp_dict.get("type") == "heartbeat":
                            inp_dict.pop("timestamp", None)
                            out_dict.pop("timestamp", None)
                        if inp_dict == out_dict:
                            matches += 1

            data_correct = (matches == received_count) if received_count > 0 else False
            checkpoints.append({
                "name": "data_correct",
                "passed": data_correct,
                "details": {"matches": matches, "received": received_count}
            })

            results["success"] = received_count >= 1 and data_correct
            results["score"] = 1.0 if results["success"] else 0.0
            results["message"] = f"Received {received_count}/{test_count} messages, {matches} matched"

        except Exception as e:
            results["message"] = f"Error: {e}"
        finally:
            for proc in [inbound_proc, outbound_proc]:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except:
                        proc.kill()

        results["details"]["checkpoints"] = checkpoints

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
