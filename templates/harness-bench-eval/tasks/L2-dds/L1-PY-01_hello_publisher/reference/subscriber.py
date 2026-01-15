#!/usr/bin/env python3
"""Reference Subscriber for HelloWorld benchmark task.

This is a VERIFIED reference implementation used to validate
AI-generated publishers. Outputs deterministic JSONL.

Uses:
- DynamicData for type definition (matches what models typically generate)
- WaitSet pattern (not polling)
- Fixed domain ID for reproducibility
"""

import argparse
import json
import sys
import time

import rti.connextdds as dds


def create_hello_world_type():
    """Create the HelloWorld type using DynamicData."""
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def run_subscriber(
    domain_id: int,
    expected_count: int,
    timeout: float,
    output_file,
) -> dict:
    """Run reference subscriber with WaitSet.

    Returns dict with counts and status.
    """
    # Create participant
    participant = dds.DomainParticipant(domain_id)

    # Create type and topic using DynamicData
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)

    # Create subscriber and reader
    subscriber = dds.Subscriber(participant)
    reader = dds.DynamicData.DataReader(subscriber, topic)

    # WaitSet pattern
    waitset = dds.WaitSet()
    condition = dds.StatusCondition(reader)
    condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
    waitset.attach_condition(condition)

    print(f"Reference subscriber started on domain {domain_id}", file=sys.stderr)
    print(f"Waiting for {expected_count} samples (timeout: {timeout}s)...", file=sys.stderr)

    samples_received = []
    start_time = time.time()

    try:
        while len(samples_received) < expected_count:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                print(f"Timeout after receiving {len(samples_received)} samples", file=sys.stderr)
                break

            wait_time = min(remaining, 1.0)
            conditions = waitset.wait(dds.Duration.from_seconds(wait_time))

            if condition in conditions:
                for sample in reader.take():
                    if sample.info.valid:
                        sample_dict = {
                            "topic": "HelloWorld",
                            "seq": len(samples_received) + 1,
                            "data": {
                                "message": sample.data["message"],
                                "count": sample.data["count"],
                            }
                        }
                        samples_received.append(sample_dict)

                        # Write to output immediately
                        output_file.write(json.dumps(sample_dict) + "\n")
                        output_file.flush()

                        print(f"  Received [{len(samples_received)}]: count={sample.data['count']}", file=sys.stderr)

                        if len(samples_received) >= expected_count:
                            break

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)

    elapsed = time.time() - start_time
    print(f"Received {len(samples_received)}/{expected_count} samples in {elapsed:.1f}s", file=sys.stderr)

    return {
        "samples_received": len(samples_received),
        "expected": expected_count,
        "success": len(samples_received) >= expected_count,
        "elapsed_seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Reference HelloWorld Subscriber")
    parser.add_argument("--domain", "-d", type=int, default=85,
                        help="DDS domain ID (default: 85)")
    parser.add_argument("--count", "-n", type=int, default=10,
                        help="Expected sample count (default: 10)")
    parser.add_argument("--timeout", "-t", type=float, default=30.0,
                        help="Timeout in seconds (default: 30)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output file for JSONL (default: stdout)")

    args = parser.parse_args()

    output_file = open(args.output, "w") if args.output else sys.stdout

    try:
        result = run_subscriber(args.domain, args.count, args.timeout, output_file)
        sys.exit(0 if result["success"] else 1)
    finally:
        if args.output:
            output_file.close()


if __name__ == "__main__":
    main()
