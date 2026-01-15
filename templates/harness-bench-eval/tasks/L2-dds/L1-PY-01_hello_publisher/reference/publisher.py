#!/usr/bin/env python3
"""Reference Publisher for HelloWorld benchmark task.

This is a VERIFIED reference implementation used to generate
expected output for benchmark validation.

This is what the AI model should produce (functionally equivalent).
"""

import argparse
import sys
import time


def create_hello_world_type():
    """Create the HelloWorld type matching task requirements."""
    import rti.connextdds as dds
    
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    
    return hello_type


def run_publisher(
    domain_id: int,
    sample_count: int,
    rate_hz: float,
) -> dict:
    """Run reference publisher.
    
    Returns dict with counts.
    """
    import rti.connextdds as dds
    
    # Create participant
    participant = dds.DomainParticipant(domain_id)
    
    # Create type and topic
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    # Create publisher and writer
    publisher = dds.Publisher(participant)
    writer = dds.DynamicData.DataWriter(publisher, topic)
    
    print(f"Reference publisher started on domain {domain_id}", file=sys.stderr)
    
    # Wait for discovery
    time.sleep(2.0)
    
    # Create sample
    sample = dds.DynamicData(hello_type)
    period = 1.0 / rate_hz if rate_hz > 0 else 0.5
    
    samples_sent = 0
    
    try:
        for i in range(sample_count):
            # Set deterministic values
            sample["message"] = f"Hello World {i + 1}"
            sample["count"] = i + 1
            
            writer.write(sample)
            samples_sent += 1
            
            print(f"  Published [{samples_sent}]: count={i + 1}", file=sys.stderr)
            
            if i < sample_count - 1:
                time.sleep(period)
                
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
    
    print(f"Published {samples_sent} samples", file=sys.stderr)
    
    # Wait for reliable delivery
    time.sleep(1.0)
    
    return {
        "samples_sent": samples_sent,
        "expected": sample_count,
        "success": samples_sent == sample_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Reference HelloWorld Publisher")
    parser.add_argument("--domain", "-d", type=int, default=85,
                        help="DDS domain ID (default: 85)")
    parser.add_argument("--count", "-n", type=int, default=10,
                        help="Sample count (default: 10)")
    parser.add_argument("--rate", "-r", type=float, default=2.0,
                        help="Publish rate in Hz (default: 2)")
    
    args = parser.parse_args()
    
    try:
        import rti.connextdds as dds
    except ImportError:
        print("ERROR: RTI Connext DDS Python API not available", file=sys.stderr)
        sys.exit(1)
    
    result = run_publisher(args.domain, args.count, args.rate)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()


