#!/usr/bin/env python3
"""Reference Subscriber using DynamicData (runtime types)."""

import argparse
import json
import sys
import time

import rti.connextdds as dds


def create_hello_world_type():
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def run_subscriber(domain_id, expected_count, timeout, output_file):
    participant = dds.DomainParticipant(domain_id)
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    subscriber = dds.Subscriber(participant)
    reader = dds.DynamicData.DataReader(subscriber, topic)
    
    waitset = dds.WaitSet()
    condition = dds.StatusCondition(reader)
    condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
    waitset.attach_condition(condition)
    
    samples_received = []
    start_time = time.time()
    
    while len(samples_received) < expected_count:
        remaining = timeout - (time.time() - start_time)
        if remaining <= 0:
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
                    output_file.write(json.dumps(sample_dict) + "\n")
                    output_file.flush()
                    
                    if len(samples_received) >= expected_count:
                        break
    
    return len(samples_received) >= expected_count, len(samples_received)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", "-d", type=int, default=85)
    parser.add_argument("--count", "-n", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()
    
    output_file = open(args.output, "w") if args.output else sys.stdout
    try:
        success, count = run_subscriber(args.domain, args.count, args.timeout, output_file)
        sys.exit(0 if success else 1)
    finally:
        if args.output:
            output_file.close()


if __name__ == "__main__":
    main()

