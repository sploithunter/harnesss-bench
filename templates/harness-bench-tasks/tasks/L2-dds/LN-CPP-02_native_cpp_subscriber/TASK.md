# Task: Create C++ DDS Subscriber

## Objective

Create a DDS subscriber in C++ using the Modern C++ API that receives messages from the "HelloWorld" topic and outputs them as JSON.

## Type Specification

| Field | IDL Type | Description |
|-------|----------|-------------|
| message | string<256> | Text message |
| count | long | Sequence number |

## Behavior

1. Parse command line: `--count N` (default 10), `--timeout T` seconds (default 30), `--domain D` (default 0)
2. Subscribe to topic "HelloWorld" on the specified domain
3. Use RELIABLE reliability, TRANSIENT_LOCAL durability, KEEP_ALL history
4. Receive samples and print each as JSON to stdout: `{"message":"...", "count":N}`
5. Exit 0 if count samples received, exit 1 otherwise

## Provided Files

- `HelloWorld.idl` - Type definition (provided)

## Required Files

1. `subscriber.cxx` - The C++ subscriber using Modern C++ API (dds:: namespace)
2. `CMakeLists.txt` - Build configuration

## Environment

- `$NDDSHOME` points to RTI Connext DDS installation
- `$CONNEXTDDS_ARCH` contains the target architecture
- `rtiddsgen -language C++11` will be run automatically before cmake
- RTI Connext DDS Modern C++ API is available

## Build

```bash
mkdir build && cd build
cmake ..
make
```

## Verification

A Python publisher will send 10 samples. Your subscriber must receive all of them and output valid JSON lines.

## Critical Requirements

- Topic name must be exactly "HelloWorld"
- Type name must be exactly "HelloWorld"
- Field names must match exactly: `message`, `count`
- Use the Modern C++ API (`dds::` namespace), not the legacy C API
- Output one JSON object per line to stdout
