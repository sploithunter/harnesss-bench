#!/usr/bin/env python3
"""Task A: Subscriber discovers Publisher's GUID.

This demonstrates how a subscriber can determine which publisher
sent each sample using the sample info metadata.
"""

import argparse
import json
import signal
import sys
import time

import rti.connextdds as dds


running = True


def signal_handler(signum, frame):
    global running
    running = False


def create_hello_type():
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def main():
    global running
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    participant = dds.DomainParticipant(args.domain)
    
    hello_type = create_hello_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    subscriber = dds.Subscriber(participant)
    
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
    
    # WaitSet pattern
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)
    
    received_count = 0
    discovered_publishers = set()
    start_time = time.time()
    
    print("Subscriber started, waiting for samples...", file=sys.stderr)
    
    while running and received_count < args.count:
        elapsed = time.time() - start_time
        remaining = args.timeout - elapsed
        
        if remaining <= 0:
            break
        
        wait_time = min(1.0, remaining)
        active = waitset.wait(dds.Duration.from_seconds(wait_time))
        
        if read_condition in active:
            for sample in reader.take():
                if sample.info.valid:
                    # Get the publication handle from sample info
                    pub_handle = sample.info.publication_handle
                    
                    # Get detailed publication data using the handle
                    try:
                        pub_data = reader.matched_publication_data(pub_handle)
                        pub_guid = str(pub_data.key)
                        discovered_publishers.add(pub_guid)
                        
                        output = {
                            "sample": {
                                "message": sample.data["message"],
                                "count": sample.data["count"],
                            },
                            "publisher_guid": pub_guid,
                        }
                        print(json.dumps(output), flush=True)
                        
                    except Exception as e:
                        # Handle case where publication data not yet available
                        print(f"Could not get pub data: {e}", file=sys.stderr)
                    
                    received_count += 1
                    
                    if received_count >= args.count:
                        break
    
    print(f"\nReceived {received_count} samples", file=sys.stderr)
    print(f"Unique publishers discovered: {len(discovered_publishers)}", file=sys.stderr)
    for guid in discovered_publishers:
        print(f"  Publisher GUID: {guid}", file=sys.stderr)


if __name__ == "__main__":
    main()


