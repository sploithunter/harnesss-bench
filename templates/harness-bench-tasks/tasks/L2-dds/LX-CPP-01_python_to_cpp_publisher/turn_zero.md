# Task: Translate Python DDS Publisher to C++

## Environment
- RTI Connext DDS 7.x is installed
- `$NDDSHOME` is set to the RTI installation directory
- `$CONNEXTDDS_ARCH` contains the target architecture
- The test harness runs `rtiddsgen` automatically before building
- Run `python test_cpp.py` to verify your solution

## The Scenario

You have a working Python DDS publisher and need to translate it to C++ while maintaining interoperability with the existing Python subscriber.

## Source Python Code (translate this)

```python
#!/usr/bin/env python3
import argparse, time, sys
import rti.connextdds as dds

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    
    participant = dds.DomainParticipant(args.domain)
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DynamicData.DataWriter(dds.Publisher(participant), topic, writer_qos)
    time.sleep(2.0)  # Discovery
    
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(hello_type)
        sample["message"] = "Hello, World!"
        sample["count"] = i
        writer.write(sample)
        if i < args.count:
            time.sleep(0.5)
    
    time.sleep(2.0)  # Reliable delivery

if __name__ == "__main__":
    main()
```

## Files to Create

### 1. HelloWorld.idl
Define the same type as the Python code uses.

### 2. publisher.cxx
Translate the Python logic to C++ using RTI Modern C++ API.

### 3. CMakeLists.txt
Build configuration for the C++ project.

## Key Translation Points

| Python | C++ |
|--------|-----|
| `dds.DomainParticipant(0)` | `dds::domain::DomainParticipant(0)` |
| `dds.StructType("...")` | IDL file + rtiddsgen |
| `writer_qos.reliability.kind = ...` | `qos << dds::core::policy::...` |
| `sample["message"] = "Hi"` | `sample.message("Hi")` |
| `time.sleep(2.0)` | `std::this_thread::sleep_for(...)` |

## Important Notes

- The test harness runs `rtiddsgen` first, so generated files will exist
- Platform defines needed: RTI_DARWIN + RTI_UNIX for macOS
- QoS must match exactly for interoperability

## Test Your Solution

Run: `python test_cpp.py`

## Action Required

Create the files `HelloWorld.idl`, `publisher.cxx`, and `CMakeLists.txt` now. Do not ask for confirmation - proceed directly to creating all three files.
