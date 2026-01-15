#!/usr/bin/env python3
"""Reference DDS Publisher using DynamicData (runtime types)."""

import argparse
import time
import sys

import rti.connextdds as dds


def create_hello_world_type():
    """Create the HelloWorld DynamicData type."""
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def main():
    parser = argparse.ArgumentParser(description="HelloWorld DDS Publisher (DynamicData)")
    parser.add_argument("--count", "-c", type=int, default=10, help="Number of samples")
    parser.add_argument("--interval", "-i", type=float, default=0.5, help="Interval between samples")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    args = parser.parse_args()
    
    participant = dds.DomainParticipant(args.domain)
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    
    time.sleep(2.0)
    
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(hello_type)
        sample["message"] = "Hello, World!"
        sample["count"] = i
        writer.write(sample)
        print(f"Published: message='Hello, World!', count={i}", file=sys.stderr)
        if i < args.count:
            time.sleep(args.interval)
    
    time.sleep(2.0)
    print(f"Published {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()

