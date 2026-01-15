# Task: Translate Python DDS Publisher to C++

## Critical Development Principle

**TEST EARLY, TEST OFTEN** - Build and test after each change. Do not write large amounts of code without testing.

## Objective

Translate the provided Python DDS publisher to C++ while maintaining exact interoperability with the existing Python subscriber.

## Environment Information

**IMPORTANT**: The following environment is pre-configured:
- `$NDDSHOME` is set to the RTI Connext DDS installation directory
- `$CONNEXTDDS_ARCH` contains the target architecture (e.g., `x64Darwin17clang9.0`)
- The test harness will run `rtiddsgen` automatically before cmake - you do NOT need to call it in CMakeLists.txt
- Generated files (`HelloWorld.hpp`, `HelloWorld.cxx`, `HelloWorldPlugin.cxx`) will be in the current directory

## Source Code to Translate

```python
#!/usr/bin/env python3
"""HelloWorld DDS Publisher - Translate this to C++"""

import argparse
import time
import sys
import rti.connextdds as dds

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    # Create type dynamically
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    
    # Create participant and topic
    participant = dds.DomainParticipant(args.domain)
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    # Create publisher with QoS
    publisher = dds.Publisher(participant)
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    
    time.sleep(2.0)  # Discovery
    
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(hello_type)
        sample["message"] = "Hello, World!"
        sample["count"] = i
        writer.write(sample)
        print(f"Published: count={i}", file=sys.stderr)
        if i < args.count:
            time.sleep(0.5)
    
    time.sleep(2.0)  # Allow reliable delivery

if __name__ == "__main__":
    main()
```

## Requirements

### 1. Create HelloWorld.idl

```idl
struct HelloWorld {
    string<256> message;
    long count;
};
```

### 2. Create publisher.cxx

Use RTI Connext DDS Modern C++ API:

```cpp
#include <dds/dds.hpp>
#include "HelloWorld.hpp"  // Generated from IDL by test harness

int main(int argc, char* argv[]) {
    // Parse args (--count, --domain)
    // Create participant
    // Create topic
    // Create writer with matching QoS
    // Publish samples
}
```

### 3. Create CMakeLists.txt

**IMPORTANT**: Use this exact CMake configuration - it is tested to work with the environment:

```cmake
cmake_minimum_required(VERSION 3.11)
project(HelloWorldPublisher)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# RTI Connext DDS paths from environment
set(NDDSHOME $ENV{NDDSHOME})
set(CONNEXTDDS_ARCH $ENV{CONNEXTDDS_ARCH})

# If arch not set, try to detect it
if(NOT CONNEXTDDS_ARCH)
    file(GLOB ARCH_DIRS "${NDDSHOME}/lib/*")
    list(GET ARCH_DIRS 0 ARCH_DIR)
    get_filename_component(CONNEXTDDS_ARCH ${ARCH_DIR} NAME)
endif()

# Platform defines required by RTI headers
if(APPLE)
    add_compile_definitions(RTI_DARWIN RTI_UNIX)
elseif(UNIX)
    add_compile_definitions(RTI_LINUX RTI_UNIX)
endif()

# Generated type support files (created by rtiddsgen before cmake runs)
set(GENERATED_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/HelloWorld.cxx
    ${CMAKE_CURRENT_SOURCE_DIR}/HelloWorldPlugin.cxx
)

add_executable(publisher
    publisher.cxx
    ${GENERATED_SOURCES}
)

target_include_directories(publisher PRIVATE
    ${NDDSHOME}/include
    ${NDDSHOME}/include/ndds
    ${NDDSHOME}/include/ndds/hpp
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_directories(publisher PRIVATE
    ${NDDSHOME}/lib/${CONNEXTDDS_ARCH}
)

target_link_libraries(publisher
    nddscpp2
    nddsc
    nddscore
    pthread
    dl
    m
)
```

## Critical: QoS Must Match

For interoperability with the Python subscriber:
- Reliability: RELIABLE
- Durability: TRANSIENT_LOCAL
- History: KEEP_ALL

## Build and Test

```bash
# Build
mkdir build && cd build
cmake ..
make

# Test (Python subscriber in separate terminal)
./publisher --count 10 --domain 0
```

## Verification

Your C++ publisher is correct when:
1. It compiles without errors
2. The Python subscriber receives all 10 samples
3. Sample content matches: message="Hello, World!", count=1..10

## Files to Create

1. `HelloWorld.idl` - Type definition
2. `publisher.cxx` - C++ publisher implementation
3. `CMakeLists.txt` - Build configuration

Run `./test_interop.sh` after building to verify interoperability.

## CRITICAL: DDS Interoperability Requirements

**Topic name must be EXACTLY `"HelloWorld"`.** Not `"HelloWorldTopic"`, not `"hello_world"`. The Python subscriber expects exactly `"HelloWorld"`. Character-for-character match required.

**Type name must be EXACTLY `"HelloWorld"`.** The struct name in your IDL must be `HelloWorld`. This determines the DDS type name.

**Field names and types must match EXACTLY.** Use `message` (string<256>) and `count` (long). The Python subscriber expects these exact field names.

**C++ (IDL-generated) and Python (DynamicData) CAN interoperate** as long as the type structure is identical. RTI's wire protocol handles the serialization differences.

## DO NOT

- Do not use the legacy C API
- Do not use XML QoS files (set QoS in code)
- Do not use `find_package(RTIConnextDDS)` - it is not available in this environment
- Do not call `connextdds_rtiddsgen()` - the test harness runs rtiddsgen automatically
- Do not change the topic name from `"HelloWorld"`


