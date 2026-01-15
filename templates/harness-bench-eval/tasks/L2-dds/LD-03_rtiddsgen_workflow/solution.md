# Solution: RTI DDS Gen Workflow

## Step 1: HelloWorld.idl

```idl
// HelloWorld.idl
struct HelloWorld {
    string<256> message;
    long count;
};
```

## Step 2: Generate with rtiddsgen

```bash
$NDDSHOME/bin/rtiddsgen -language python -d . HelloWorld.idl
```

## Step 3: publisher.py

```python
#!/usr/bin/env python3
"""Publisher using rtiddsgen-generated types."""

import time
import rti.connextdds as dds
from HelloWorld import HelloWorld  # Generated type

def main():
    participant = dds.DomainParticipant(0)
    
    # Use generated type directly
    topic = dds.Topic(participant, "HelloWorld", HelloWorld)
    
    publisher = dds.Publisher(participant)
    writer = dds.DataWriter(publisher, topic)
    
    time.sleep(2.0)  # Discovery
    
    for i in range(1, 11):
        sample = HelloWorld()
        sample.message = f"Hello World {i}"
        sample.count = i
        writer.write(sample)
        time.sleep(0.5)
    
    time.sleep(1.0)
    print(f"Published 10 samples")

if __name__ == "__main__":
    main()
```

## Step 4: subscriber.py

```python
#!/usr/bin/env python3
"""Subscriber using rtiddsgen-generated types."""

import argparse
import json
import signal
import sys
import rti.connextdds as dds
from HelloWorld import HelloWorld

running = True

def signal_handler(signum, frame):
    global running
    running = False

def main():
    global running
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    args = parser.parse_args()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    participant = dds.DomainParticipant(0)
    topic = dds.Topic(participant, "HelloWorld", HelloWorld)
    
    subscriber = dds.Subscriber(participant)
    reader = dds.DataReader(subscriber, topic)
    
    waitset = dds.WaitSet()
    condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(condition)
    
    received = 0
    import time
    start = time.time()
    
    while running and received < args.count and (time.time() - start) < args.timeout:
        active = waitset.wait(dds.Duration.from_seconds(1.0))
        if condition in active:
            for sample in reader.take():
                if sample.info.valid:
                    output = {
                        "message": sample.data.message,
                        "count": sample.data.count,
                    }
                    print(json.dumps(output), flush=True)
                    received += 1

if __name__ == "__main__":
    main()
```

## Key Differences from DynamicData

| Aspect | DynamicData | Generated Types |
|--------|-------------|-----------------|
| Topic | `dds.DynamicData.Topic()` | `dds.Topic()` |
| Writer | `dds.DynamicData.DataWriter()` | `dds.DataWriter()` |
| Reader | `dds.DynamicData.DataReader()` | `dds.DataReader()` |
| Sample creation | `dds.DynamicData(type)` | `HelloWorld()` |
| Field access | `sample["field"]` | `sample.field` |

