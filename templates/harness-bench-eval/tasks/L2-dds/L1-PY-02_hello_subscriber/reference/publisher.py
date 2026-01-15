#!/usr/bin/env python3
"""Reference DDS Publisher for HelloWorld topic.

This publisher is used to test AI-generated subscribers.
Uses @idl.struct for type definition (modern API that models tend to use).
"""

import argparse
import time
import sys

import rti.connextdds as dds
import rti.idl as idl


@idl.struct(member_annotations={'message': [idl.bound(256)]})
class HelloWorld:
    message: str = ""
    count: int = 0


def main():
    parser = argparse.ArgumentParser(description="HelloWorld DDS Publisher")
    parser.add_argument("--count", "-c", type=int, default=10, help="Number of samples")
    parser.add_argument("--interval", "-i", type=float, default=0.5, help="Interval between samples")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    args = parser.parse_args()
    
    # Create participant
    participant = dds.DomainParticipant(args.domain)
    
    # Create topic using IDL-defined type
    topic = dds.Topic(participant, "HelloWorld", HelloWorld)
    
    # Create publisher and writer with RELIABLE + TRANSIENT_LOCAL QoS
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DataWriter(publisher, topic, writer_qos)
    
    # Wait for subscriber discovery
    time.sleep(2.0)
    
    # Publish samples
    for i in range(1, args.count + 1):
        sample = HelloWorld(message="Hello, World!", count=i)
        
        writer.write(sample)
        print(f"Published: message='Hello, World!', count={i}", file=sys.stderr)
        
        if i < args.count:
            time.sleep(args.interval)
    
    # Allow time for reliable delivery
    time.sleep(2.0)
    
    print(f"Published {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()
