# Task: Create C++ DDS Publisher from Scratch

## Critical Development Principle

**TEST EARLY, TEST OFTEN** - Build and test after each step. Don't write everything before testing.

## Objective

Create a DDS publisher in C++ that publishes to the "HelloWorld" topic.
Your publisher must interoperate with a Python subscriber (provided for testing).

**You are NOT given any source code to translate. Create this from scratch.**

## Environment Information

**IMPORTANT**: The following environment is pre-configured:
- `$NDDSHOME` is set to the RTI Connext DDS installation directory
- `$CONNEXTDDS_ARCH` contains the target architecture (e.g., `x64Darwin17clang9.0`)
- The test harness will run `rtiddsgen` automatically before cmake - you do NOT need to call it in CMakeLists.txt
- Generated files (`HelloWorld.hpp`, `HelloWorld.cxx`, `HelloWorldPlugin.cxx`) will be in the current directory

## Type Specification

Create a DDS type with these exact fields:

| Field | Type | Notes |
|-------|------|-------|
| message | string | max length 256 |
| count | int32 | sequence number (use `long` in IDL) |

## QoS Requirements

For interoperability with the test subscriber:

| QoS Policy | Setting |
|------------|---------|
| Reliability | RELIABLE |
| Durability | TRANSIENT_LOCAL |
| History | KEEP_ALL |

## Behavior

1. Parse command line: `--count N` (default 10), `--domain D` (default 0)
2. Create DomainParticipant on specified domain
3. Create Topic "HelloWorld" with the type above
4. Create DataWriter with QoS settings above
5. Wait 2 seconds for subscriber discovery
6. Publish N samples:
   - message = "Hello, World!"
   - count = 1, 2, 3, ... N
   - 500ms delay between samples
7. Wait 2 seconds for reliable delivery
8. Exit cleanly

## Required Files

### 1. HelloWorld.idl

Define the DDS type in IDL format:
```idl
struct HelloWorld {
    string<256> message;
    long count;
};
```

### 2. publisher.cxx

The C++ publisher using RTI Connext DDS Modern C++ API.

Key includes:
```cpp
#include <dds/dds.hpp>
#include "HelloWorld.hpp"  // Generated from IDL by test harness
```

### 3. CMakeLists.txt

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

## Build Instructions

```bash
mkdir build && cd build
cmake ..
make
```

## Verification

Your publisher is correct when:
1. It compiles without errors
2. Running `./publisher --count 10` successfully publishes
3. The Python test subscriber receives all 10 samples
4. Sample content: message="Hello, World!", count=1..10

Run `./test_interop.sh` to verify interoperability.

## Hints

- RTI Modern C++ API uses `dds::` namespace
- QoS is set via stream operators: `qos << dds::core::policy::Reliability::Reliable()`
- Type-safe DataWriter: `dds::pub::DataWriter<HelloWorld>`
- Sample fields accessed via generated methods: `sample.message("Hello")`

## CRITICAL: DDS Interoperability Requirements

**Topic name must be EXACTLY `"HelloWorld"`.** Not `"HelloWorldTopic"`, not `"hello_world"`. The Python test subscriber expects exactly `"HelloWorld"`. Character-for-character match required.

**Type name must be EXACTLY `"HelloWorld"`.** The struct name in your IDL must be `HelloWorld`. This determines the DDS type name.

**Field names and types must match EXACTLY.** Use `message` (string<256>) and `count` (long). The Python subscriber expects these exact field names.

## DO NOT

- Do not use the legacy C API
- Do not use XML QoS files (set QoS in code)
- Do not use `find_package(RTIConnextDDS)` - it is not available in this environment
- Do not call `connextdds_rtiddsgen()` - the test harness runs rtiddsgen automatically
- Do not change the topic name from `"HelloWorld"`


