#!/usr/bin/env python3
"""Inbound Adapter: Binary Protocol → DDS.

Reads binary messages from a file/pipe and publishes to DDS topics.
Each message type maps to a separate DDS topic.
"""

import argparse
import json
import os
import sys
import time

import rti.connextdds as dds

# Import protocol from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import decode_message, Heartbeat, Position, Command


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
    command_type.add_member(dds.Member("params_json", dds.StringType(1024)))  # JSON-encoded params
    
    return heartbeat_type, position_type, command_type


def main():
    parser = argparse.ArgumentParser(description="Binary → DDS Inbound Adapter")
    parser.add_argument("--input", "-i", required=True, help="Input binary file")
    parser.add_argument("--domain", "-d", type=int, default=0, help="DDS domain ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    # Create DDS participant
    participant = dds.DomainParticipant(args.domain)
    
    # Create types and topics
    heartbeat_type, position_type, command_type = create_dds_types()
    
    heartbeat_topic = dds.DynamicData.Topic(participant, "Heartbeat", heartbeat_type)
    position_topic = dds.DynamicData.Topic(participant, "Position", position_type)
    command_topic = dds.DynamicData.Topic(participant, "Command", command_type)
    
    # Create publisher and writers
    publisher = dds.Publisher(participant)
    
    # Use RELIABLE + TRANSIENT_LOCAL for late-joiner support
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    heartbeat_writer = dds.DynamicData.DataWriter(publisher, heartbeat_topic, writer_qos)
    position_writer = dds.DynamicData.DataWriter(publisher, position_topic, writer_qos)
    command_writer = dds.DynamicData.DataWriter(publisher, command_topic, writer_qos)
    
    # Read binary file
    with open(args.input, "rb") as f:
        data = f.read()
    
    if args.verbose:
        print(f"Read {len(data)} bytes from {args.input}", file=sys.stderr)
    
    # Parse and publish messages
    published_count = 0
    
    while data:
        try:
            msg, data = decode_message(data)
            
            if isinstance(msg, Heartbeat):
                sample = dds.DynamicData(heartbeat_type)
                sample["seq"] = msg.seq
                sample["timestamp"] = msg.timestamp
                heartbeat_writer.write(sample)
                
            elif isinstance(msg, Position):
                sample = dds.DynamicData(position_type)
                sample["id"] = msg.id
                sample["x"] = msg.x
                sample["y"] = msg.y
                sample["z"] = msg.z
                position_writer.write(sample)
                
            elif isinstance(msg, Command):
                sample = dds.DynamicData(command_type)
                sample["id"] = msg.id
                sample["action"] = msg.action
                sample["params_json"] = json.dumps(msg.params)
                command_writer.write(sample)
            
            published_count += 1
            
            if args.verbose:
                print(f"Published: {msg}", file=sys.stderr)
                
        except ValueError as e:
            print(f"Error parsing message: {e}", file=sys.stderr)
            break
    
    # Allow time for reliable delivery and acknowledgment
    time.sleep(2.0)
    
    print(f"Published {published_count} messages to DDS", file=sys.stderr)


if __name__ == "__main__":
    main()

