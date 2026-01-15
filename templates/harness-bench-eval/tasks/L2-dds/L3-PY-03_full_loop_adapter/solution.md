# Solution: Full Loop Binary Protocol Adapter

## inbound_adapter.py (Binary → DDS)

```python
#!/usr/bin/env python3
"""Inbound Adapter: Binary Protocol → DDS."""

import argparse
import json
import os
import sys
import time

import rti.connextdds as dds

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import decode_message, Heartbeat, Position, Command


def create_dds_types():
    heartbeat_type = dds.StructType("Heartbeat")
    heartbeat_type.add_member(dds.Member("seq", dds.Int32Type()))
    heartbeat_type.add_member(dds.Member("timestamp", dds.Float64Type()))
    
    position_type = dds.StructType("Position")
    position_type.add_member(dds.Member("id", dds.Int32Type()))
    position_type.add_member(dds.Member("x", dds.Float64Type()))
    position_type.add_member(dds.Member("y", dds.Float64Type()))
    position_type.add_member(dds.Member("z", dds.Float64Type()))
    
    command_type = dds.StructType("Command")
    command_type.add_member(dds.Member("id", dds.Int32Type()))
    command_type.add_member(dds.Member("action", dds.StringType(256)))
    command_type.add_member(dds.Member("params_json", dds.StringType(1024)))
    
    return heartbeat_type, position_type, command_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    participant = dds.DomainParticipant(args.domain)
    
    heartbeat_type, position_type, command_type = create_dds_types()
    
    heartbeat_topic = dds.DynamicData.Topic(participant, "Heartbeat", heartbeat_type)
    position_topic = dds.DynamicData.Topic(participant, "Position", position_type)
    command_topic = dds.DynamicData.Topic(participant, "Command", command_type)
    
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    heartbeat_writer = dds.DynamicData.DataWriter(publisher, heartbeat_topic, writer_qos)
    position_writer = dds.DynamicData.DataWriter(publisher, position_topic, writer_qos)
    command_writer = dds.DynamicData.DataWriter(publisher, command_topic, writer_qos)
    
    with open(args.input, "rb") as f:
        data = f.read()
    
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
                
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            break
    
    time.sleep(2.0)
    print(f"Published {published_count} messages", file=sys.stderr)


if __name__ == "__main__":
    main()
```

## outbound_adapter.py (DDS → Binary)

```python
#!/usr/bin/env python3
"""Outbound Adapter: DDS → Binary Protocol."""

import argparse
import json
import os
import sys
import time

import rti.connextdds as dds

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import encode_message, Heartbeat, Position, Command


def create_dds_types():
    heartbeat_type = dds.StructType("Heartbeat")
    heartbeat_type.add_member(dds.Member("seq", dds.Int32Type()))
    heartbeat_type.add_member(dds.Member("timestamp", dds.Float64Type()))
    
    position_type = dds.StructType("Position")
    position_type.add_member(dds.Member("id", dds.Int32Type()))
    position_type.add_member(dds.Member("x", dds.Float64Type()))
    position_type.add_member(dds.Member("y", dds.Float64Type()))
    position_type.add_member(dds.Member("z", dds.Float64Type()))
    
    command_type = dds.StructType("Command")
    command_type.add_member(dds.Member("id", dds.Int32Type()))
    command_type.add_member(dds.Member("action", dds.StringType(256)))
    command_type.add_member(dds.Member("params_json", dds.StringType(1024)))
    
    return heartbeat_type, position_type, command_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--domain", "-d", type=int, default=0)
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    args = parser.parse_args()
    
    messages = []
    
    participant = dds.DomainParticipant(args.domain)
    
    heartbeat_type, position_type, command_type = create_dds_types()
    
    heartbeat_topic = dds.DynamicData.Topic(participant, "Heartbeat", heartbeat_type)
    position_topic = dds.DynamicData.Topic(participant, "Position", position_type)
    command_topic = dds.DynamicData.Topic(participant, "Command", command_type)
    
    subscriber = dds.Subscriber(participant)
    
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    heartbeat_reader = dds.DynamicData.DataReader(subscriber, heartbeat_topic, reader_qos)
    position_reader = dds.DynamicData.DataReader(subscriber, position_topic, reader_qos)
    command_reader = dds.DynamicData.DataReader(subscriber, command_topic, reader_qos)
    
    # WaitSet pattern - async, not polling!
    waitset = dds.WaitSet()
    
    hb_cond = dds.ReadCondition(heartbeat_reader, dds.DataState.any_data)
    pos_cond = dds.ReadCondition(position_reader, dds.DataState.any_data)
    cmd_cond = dds.ReadCondition(command_reader, dds.DataState.any_data)
    
    waitset.attach_condition(hb_cond)
    waitset.attach_condition(pos_cond)
    waitset.attach_condition(cmd_cond)
    
    start_time = time.time()
    
    while len(messages) < args.count:
        elapsed = time.time() - start_time
        if elapsed > args.timeout:
            break
        
        active = waitset.wait(dds.Duration.from_seconds(1.0))
        
        for cond in active:
            if cond == hb_cond:
                for s in heartbeat_reader.take():
                    if s.info.valid:
                        messages.append(Heartbeat(s.data["seq"], s.data["timestamp"]))
            elif cond == pos_cond:
                for s in position_reader.take():
                    if s.info.valid:
                        messages.append(Position(s.data["id"], s.data["x"], s.data["y"], s.data["z"]))
            elif cond == cmd_cond:
                for s in command_reader.take():
                    if s.info.valid:
                        messages.append(Command(s.data["id"], s.data["action"], json.loads(s.data["params_json"])))
    
    with open(args.output, "wb") as f:
        for msg in messages:
            f.write(encode_message(msg))
    
    print(f"Wrote {len(messages)} messages", file=sys.stderr)


if __name__ == "__main__":
    main()
```

## Key Points

1. **TRANSIENT_LOCAL durability** - Handles any startup order
2. **RELIABLE + KEEP_ALL** - No data loss
3. **WaitSet pattern** - Async reception, not polling
4. **Multiple topics** - One per message type
5. **JSON for params** - Complex dict stored as JSON string


