#!/usr/bin/env python3
"""Outbound Adapter: DDS → Binary Protocol.

Subscribes to DDS topics and writes binary messages to output file.
Uses async callbacks (WaitSet pattern) as required by DDS best practices.
"""

import argparse
import json
import os
import sys
import time
from threading import Event

import rti.connextdds as dds

# Import protocol from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import encode_message, Heartbeat, Position, Command


def create_dds_types():
    """Create DynamicData types for each message type."""
    
    # Heartbeat type
    heartbeat_type = dds.StructType("Heartbeat")
    heartbeat_type.add_member(dds.Member("seq", dds.Int32Type()))
    heartbeat_type.add_member(dds.Member("timestamp", dds.Float64Type()))
    
    # Position type
    position_type = dds.StructType("Position")
    position_type.add_member(dds.Member("id", dds.Int32Type()))
    position_type.add_member(dds.Member("x", dds.Float64Type()))
    position_type.add_member(dds.Member("y", dds.Float64Type()))
    position_type.add_member(dds.Member("z", dds.Float64Type()))
    
    # Command type
    command_type = dds.StructType("Command")
    command_type.add_member(dds.Member("id", dds.Int32Type()))
    command_type.add_member(dds.Member("action", dds.StringType(256)))
    command_type.add_member(dds.Member("params_json", dds.StringType(1024)))
    
    return heartbeat_type, position_type, command_type


def main():
    parser = argparse.ArgumentParser(description="DDS → Binary Outbound Adapter")
    parser.add_argument("--output", "-o", required=True, help="Output binary file")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    parser.add_argument("--count", "-c", type=int, default=10, help="Expected message count")
    parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    # Track received messages
    messages = []
    received_event = Event()
    
    # Create DDS participant
    participant = dds.DomainParticipant(args.domain)
    
    # Create types and topics
    heartbeat_type, position_type, command_type = create_dds_types()
    
    heartbeat_topic = dds.DynamicData.Topic(participant, "Heartbeat", heartbeat_type)
    position_topic = dds.DynamicData.Topic(participant, "Position", position_type)
    command_topic = dds.DynamicData.Topic(participant, "Command", command_type)
    
    # Create subscriber and readers with RELIABLE QoS
    subscriber = dds.Subscriber(participant)
    
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    heartbeat_reader = dds.DynamicData.DataReader(subscriber, heartbeat_topic, reader_qos)
    position_reader = dds.DynamicData.DataReader(subscriber, position_topic, reader_qos)
    command_reader = dds.DynamicData.DataReader(subscriber, command_topic, reader_qos)
    
    # Create WaitSet with read conditions
    waitset = dds.WaitSet()
    
    heartbeat_condition = dds.ReadCondition(heartbeat_reader, dds.DataState.any_data)
    position_condition = dds.ReadCondition(position_reader, dds.DataState.any_data)
    command_condition = dds.ReadCondition(command_reader, dds.DataState.any_data)
    
    waitset.attach_condition(heartbeat_condition)
    waitset.attach_condition(position_condition)
    waitset.attach_condition(command_condition)
    
    def process_heartbeats():
        samples = heartbeat_reader.take()
        for sample in samples:
            if sample.info.valid:
                msg = Heartbeat(
                    seq=sample.data["seq"],
                    timestamp=sample.data["timestamp"]
                )
                messages.append(msg)
                if args.verbose:
                    print(f"Received: {msg}", file=sys.stderr)
    
    def process_positions():
        samples = position_reader.take()
        for sample in samples:
            if sample.info.valid:
                msg = Position(
                    id=sample.data["id"],
                    x=sample.data["x"],
                    y=sample.data["y"],
                    z=sample.data["z"]
                )
                messages.append(msg)
                if args.verbose:
                    print(f"Received: {msg}", file=sys.stderr)
    
    def process_commands():
        samples = command_reader.take()
        for sample in samples:
            if sample.info.valid:
                msg = Command(
                    id=sample.data["id"],
                    action=sample.data["action"],
                    params=json.loads(sample.data["params_json"])
                )
                messages.append(msg)
                if args.verbose:
                    print(f"Received: {msg}", file=sys.stderr)
    
    # Wait for messages
    start_time = time.time()
    
    while len(messages) < args.count:
        elapsed = time.time() - start_time
        remaining = args.timeout - elapsed
        
        if remaining <= 0:
            print(f"Timeout: received {len(messages)}/{args.count} messages", file=sys.stderr)
            break
        
        # Wait for data (max 1 second at a time)
        wait_time = min(1.0, remaining)
        active_conditions = waitset.wait(dds.Duration.from_seconds(wait_time))
        
        for condition in active_conditions:
            if condition == heartbeat_condition:
                process_heartbeats()
            elif condition == position_condition:
                process_positions()
            elif condition == command_condition:
                process_commands()
    
    # Write binary output
    with open(args.output, "wb") as f:
        for msg in messages:
            f.write(encode_message(msg))
    
    print(f"Wrote {len(messages)} messages to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()

