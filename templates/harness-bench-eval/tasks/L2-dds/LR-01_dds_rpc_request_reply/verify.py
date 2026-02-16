#!/usr/bin/env python3
"""Verification script for LR-01_dds_rpc_request_reply.

Model creates client.py that:
- Defines CalculatorRequest and CalculatorReply types
- Creates an rti.rpc.Requester
- Sends calculation requests
- Receives and outputs results

Test workflow:
1. Check client.py exists and has valid syntax
2. Start Calculator service (Replier)
3. Run client.py with different operations
4. Verify correct results received

PRIVATE - This file is in the eval repo and should never be in the workspace.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import rti.connextdds as dds
import rti.types as idl
from rti.rpc import Replier

from harness_bench.evaluation import check_syntax, check_dds_shmem


# Define the types that the service uses
@idl.struct(
    member_annotations={
        'operation': [idl.bound(64)],
    }
)
class CalculatorRequest:
    operation: str = ""
    a: int = 0
    b: int = 0


@idl.struct(
    member_annotations={
        'error': [idl.bound(256)],
    }
)
class CalculatorReply:
    result: int = 0
    success: bool = False
    error: str = ""


class CalculatorService:
    """Simple calculator service for testing"""

    def __init__(self, domain_id=0):
        self.participant = dds.DomainParticipant(domain_id)
        self.replier = Replier(
            request_type=CalculatorRequest,
            reply_type=CalculatorReply,
            participant=self.participant,
            service_name="CalculatorService"
        )
        self.running = False

    def handle_request(self, request):
        """Process a calculation request"""
        reply = CalculatorReply()

        try:
            op = request.operation.lower()
            a, b = request.a, request.b

            if op == "add":
                reply.result = a + b
                reply.success = True
            elif op == "subtract":
                reply.result = a - b
                reply.success = True
            elif op == "multiply":
                reply.result = a * b
                reply.success = True
            else:
                reply.success = False
                reply.error = f"Unknown operation: {op}"
        except Exception as e:
            reply.success = False
            reply.error = str(e)

        return reply

    def run(self, duration=30):
        """Run the service for a duration"""
        self.running = True
        start = time.time()

        while self.running and (time.time() - start) < duration:
            try:
                requests = self.replier.receive_requests(
                    max_wait=dds.Duration(seconds=1)
                )
                for request_sample in requests:
                    if request_sample.info.valid:
                        reply = self.handle_request(request_sample.data)
                        self.replier.send_reply(reply, request_sample.info)
            except dds.TimeoutError:
                pass
            except Exception as e:
                print(f"Service error: {e}", file=sys.stderr)

    def stop(self):
        self.running = False

    def close(self):
        self.replier.close()
        self.participant.close()


def run_client_test(client_file, workspace, op, a, b, expected):
    """Run client with given operation and check result"""
    try:
        proc = subprocess.run(
            [sys.executable, str(client_file), "--op", op, "--a", str(a), "--b", str(b)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=workspace,
        )

        # Parse output
        stdout = proc.stdout.strip()
        if not stdout:
            return False, 0, f"No output (stderr: {proc.stderr[:200]})"

        try:
            result = json.loads(stdout)
            actual = result.get("result", 0)
            success = result.get("success", False)

            if success and actual == expected:
                return True, actual, None
            elif not success:
                return False, actual, f"Client reported failure: {result.get('error', 'unknown')}"
            else:
                return False, actual, f"Wrong result: expected {expected}, got {actual}"
        except json.JSONDecodeError:
            return False, 0, f"Invalid JSON output: {stdout[:100]}"

    except subprocess.TimeoutExpired:
        return False, 0, "Client timed out"
    except Exception as e:
        return False, 0, str(e)


def verify() -> dict:
    """Run verification and return results."""
    workspace = Path.cwd()

    results = {
        "success": False,
        "score": 0.0,
        "message": "",
        "details": {},
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

    # Check client.py exists
    client_file = workspace / "client.py"
    if not client_file.exists():
        results["message"] = "client.py not found"
        checkpoints.append({"name": "files_exist", "passed": False})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "files_exist", "passed": True})

    # Check syntax
    passed, error = check_syntax(client_file)
    if not passed:
        results["message"] = f"Syntax error in client.py: {error}"
        checkpoints.append({"name": "syntax", "passed": False, "details": {"error": error}})
        results["details"]["checkpoints"] = checkpoints
        return results

    checkpoints.append({"name": "syntax", "passed": True})

    # Check for required imports/patterns
    with open(client_file) as f:
        code = f.read()

    has_rpc_import = "rti.rpc" in code or "from rti import rpc" in code
    has_idl_struct = "@idl.struct" in code or "idl.struct" in code
    has_requester = "Requester" in code

    checkpoints.append({
        "name": "code_patterns",
        "passed": has_rpc_import and has_idl_struct and has_requester,
        "details": {
            "has_rpc_import": has_rpc_import,
            "has_idl_struct": has_idl_struct,
            "has_requester": has_requester,
        }
    })

    # Start Calculator service
    service = None
    service_thread = None

    try:
        service = CalculatorService(domain_id=0)
        service_thread = threading.Thread(target=service.run, args=(60,))
        service_thread.start()

        # Wait for service to be ready
        time.sleep(2)

        # Test cases
        test_cases = [
            ("add", 10, 5, 15),
            ("subtract", 20, 7, 13),
            ("multiply", 6, 8, 48),
            ("add", 100, 200, 300),
        ]

        passed_tests = 0
        test_results = []

        for op, a, b, expected in test_cases:
            passed, actual, error = run_client_test(client_file, workspace, op, a, b, expected)
            test_results.append({
                "operation": op,
                "a": a,
                "b": b,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "error": error,
            })
            if passed:
                passed_tests += 1

        checkpoints.append({
            "name": "rpc_tests",
            "passed": passed_tests == len(test_cases),
            "details": {
                "passed": passed_tests,
                "total": len(test_cases),
                "tests": test_results,
            }
        })

        # Final result
        all_critical_passed = all(
            cp.get("passed") for cp in checkpoints
            if cp.get("name") in ["files_exist", "syntax", "rpc_tests"]
        )

        results["success"] = all_critical_passed
        results["score"] = 1.0 if results["success"] else 0.0
        results["message"] = f"DDS RPC test: {passed_tests}/{len(test_cases)} operations passed"
        results["details"]["passed_tests"] = passed_tests
        results["details"]["total_tests"] = len(test_cases)
        results["details"]["checkpoints"] = checkpoints

    except Exception as e:
        results["message"] = f"Error: {e}"
        results["score"] = 0.0
        results["details"]["checkpoints"] = checkpoints

    finally:
        # Cleanup
        if service:
            service.stop()
        if service_thread:
            service_thread.join(timeout=5)
        if service:
            try:
                service.close()
            except:
                pass

    return results


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
