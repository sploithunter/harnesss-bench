# SOLUTION - Development/Testing Only
# This file should NEVER be visible to models during actual benchmarking

## Complete Working Solution

Create `subscriber.py` with EXACTLY this content:

```python
#!/usr/bin/env python3
import argparse
import json
import signal
import time
import rti.connextdds as dds

running = True

def signal_handler(signum, frame):
    global running
    running = False

def create_hello_world_type():
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type

def main():
    global running
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    args = parser.parse_args()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    participant = dds.DomainParticipant(0)
    hello_type = create_hello_world_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    subscriber = dds.Subscriber(participant)
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
    
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)
    
    received = 0
    start = time.time()
    
    while running and received < args.count:
        if time.time() - start > args.timeout:
            break
        
        active = waitset.wait(dds.Duration.from_seconds(1.0))
        if read_condition in active:
            for sample in reader.take():
                if sample.info.valid:
                    print(json.dumps({
                        "message": sample.data["message"],
                        "count": sample.data["count"]
                    }), flush=True)
                    received += 1
                    if received >= args.count:
                        break

if __name__ == "__main__":
    main()
```

## Key Points
- Domain ID: 0
- Uses WaitSet pattern (async, NOT polling)
- JSONL output to stdout
- Signal handling for graceful shutdown


