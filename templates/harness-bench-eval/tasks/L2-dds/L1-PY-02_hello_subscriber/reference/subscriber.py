#!/usr/bin/env python3
"""Reference DDS Subscriber for HelloWorld topic.

This is the gold-standard implementation that AI models should aim to replicate.
Uses WaitSet pattern (async callbacks) as required.
"""

import argparse
import json
import signal
import sys
import time

import rti.connextdds as dds


# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global running
    running = False


def create_hello_world_type():
    """Create the HelloWorld DynamicData type."""
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def main():
    global running
    
    parser = argparse.ArgumentParser(description="HelloWorld DDS Subscriber")
    parser.add_argument("--count", "-c", type=int, default=10, help="Samples to receive")
    parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Timeout seconds")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    args = parser.parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create participant
    participant = dds.DomainParticipant(args.domain)
    
    # Create topic
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    # Create subscriber and reader with matching QoS
    subscriber = dds.Subscriber(participant)
    
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
    
    # Setup WaitSet with ReadCondition (ASYNC pattern - NOT polling!)
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)
    
    received_count = 0
    start_time = time.time()
    
    while running and received_count < args.count:
        elapsed = time.time() - start_time
        remaining = args.timeout - elapsed
        
        if remaining <= 0:
            print(f"Timeout: received {received_count}/{args.count}", file=sys.stderr)
            break
        
        # Wait for data (async - blocks until data available or timeout)
        wait_time = min(1.0, remaining)
        active_conditions = waitset.wait(dds.Duration.from_seconds(wait_time))
        
        if read_condition in active_conditions:
            # Take all available samples
            for sample in reader.take():
                if sample.info.valid:
                    # Output as JSONL to stdout
                    output = {
                        "message": sample.data["message"],
                        "count": sample.data["count"],
                    }
                    print(json.dumps(output), flush=True)
                    received_count += 1
                    
                    if received_count >= args.count:
                        break
    
    print(f"Received {received_count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()


