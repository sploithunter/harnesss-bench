# Solution: Discovery GUID Mining

## Task A: subscriber_gets_pub_guid.py

```python
#!/usr/bin/env python3
"""Subscriber that discovers the GUID of the publisher for each sample."""

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
    
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)
    
    received_count = 0
    discovered_publishers = set()
    start_time = time.time()
    
    while running and received_count < args.count:
        elapsed = time.time() - start_time
        if elapsed > args.timeout:
            break
        
        active = waitset.wait(dds.Duration.from_seconds(1.0))
        
        if read_condition in active:
            for sample in reader.take():
                if sample.info.valid:
                    # Get publication handle from sample info
                    pub_handle = sample.info.publication_handle
                    
                    # Get publication data using the handle
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
                        print(f"Could not get pub data: {e}", file=sys.stderr)
                    
                    received_count += 1
                    if received_count >= args.count:
                        break

if __name__ == "__main__":
    main()
```

## Task B: publisher_gets_sub_guids.py

```python
#!/usr/bin/env python3
"""Publisher that discovers subscriber GUIDs before publishing."""

import argparse
import json
import sys
import time
import rti.connextdds as dds

def create_hello_type():
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type

def discover_subscribers(reader, topic_name, timeout=10.0):
    """Discover all subscribers to the given topic using matched_subscriptions."""
    discovered = []
    start = time.time()
    
    while time.time() - start < timeout:
        # Get currently matched subscriptions
        matched_subs = reader.matched_subscriptions
        
        for sub_handle in matched_subs:
            try:
                sub_data = reader.matched_subscription_data(sub_handle)
                guid = str(sub_data.key)
                if guid not in [d["guid"] for d in discovered]:
                    discovered.append({
                        "guid": guid,
                        "topic": topic_name,
                    })
            except:
                pass
        
        if discovered:
            break
        time.sleep(0.5)
    
    return discovered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", "-d", type=int, default=0)
    parser.add_argument("--count", "-c", type=int, default=10)
    args = parser.parse_args()
    
    participant = dds.DomainParticipant(args.domain)
    
    hello_type = create_hello_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    
    # Wait for and discover subscribers
    print("Waiting for subscribers...", file=sys.stderr)
    time.sleep(3.0)  # Give time for discovery
    
    # Get matched subscriptions
    matched_subs = writer.matched_subscriptions
    print(f"Found {len(matched_subs)} subscriber(s)", file=sys.stderr)
    
    for sub_handle in matched_subs:
        try:
            sub_data = writer.matched_subscription_data(sub_handle)
            print(json.dumps({
                "type": "discovered_subscriber",
                "guid": str(sub_data.key),
            }), flush=True)
        except Exception as e:
            print(f"Error getting sub data: {e}", file=sys.stderr)
    
    # Now publish
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(hello_type)
        sample["message"] = f"Hello World {i}"
        sample["count"] = i
        writer.write(sample)
        time.sleep(0.5)
    
    time.sleep(1.0)
    print(f"Published {args.count} samples", file=sys.stderr)

if __name__ == "__main__":
    main()
```

## Key Concepts

1. **sample.info.publication_handle**: Identifies which writer sent a sample
2. **reader.matched_publication_data(handle)**: Gets details about a matched writer
3. **writer.matched_subscriptions**: List of handles for matched readers
4. **writer.matched_subscription_data(handle)**: Gets details about a matched reader
5. **pub_data.key / sub_data.key**: The GUID of the entity


