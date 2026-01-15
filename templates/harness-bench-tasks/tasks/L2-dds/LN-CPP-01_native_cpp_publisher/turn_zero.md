# Task: Create C++ DDS Publisher from Scratch

## Environment
- RTI Connext DDS 7.x is installed
- `$NDDSHOME` is set to the RTI installation directory
- `$CONNEXTDDS_ARCH` contains the target architecture (e.g., `arm64Darwin20clang12.0`)
- The test harness runs `rtiddsgen` automatically before building
- Run `python test_cpp.py` to verify your solution

## The Scenario

You need to create a DDS publisher in C++ that publishes "HelloWorld" messages. The publisher must interoperate with a Python subscriber for testing.

## Files to Create

### 1. HelloWorld.idl

Define a DDS type with:
- `message`: string (max 256 characters)
- `count`: 32-bit integer

### 2. publisher.cxx

Create a C++ publisher using RTI Connext DDS Modern C++ API:
- Parse command line: `--count N` (default 10), `--domain D` (default 0)
- Create a DomainParticipant, Topic, Publisher, DataWriter
- Wait for subscriber discovery (2 seconds)
- Publish N samples with message="Hello, World!" and count=1,2,3...N
- 500ms delay between samples
- Wait for reliable delivery (2 seconds) before exit

QoS requirements for interoperability:
- Reliability: RELIABLE
- Durability: TRANSIENT_LOCAL
- History: KEEP_ALL

### 3. CMakeLists.txt

Build configuration that:
- Uses C++11 standard
- Finds RTI libraries using `$NDDSHOME` environment variable
- Links against `nddscpp2`, `nddsc`, `nddscore`
- Handles platform-specific defines (RTI_DARWIN/RTI_UNIX for macOS, RTI_LINUX/RTI_UNIX for Linux)

**Important**: The test harness runs `rtiddsgen` before cmake, so generated files (`HelloWorld.cxx`, `HelloWorldPlugin.cxx`) will already exist in the source directory.

## RTI Modern C++ API Hints

- Include: `<dds/dds.hpp>`
- Namespace: `dds::`
- QoS uses stream operators: `qos << dds::core::policy::Reliability::Reliable()`
- Type-safe DataWriter: `dds::pub::DataWriter<HelloWorld>`

## Build Process

The test harness does:
```bash
rtiddsgen -language C++11 HelloWorld.idl  # Generates type support
mkdir build && cd build
cmake ..
make
./publisher --count 10
```

## Test Your Solution

Run: `python test_cpp.py`

## Action Required

Create the files `HelloWorld.idl`, `publisher.cxx`, and `CMakeLists.txt` now. Do not ask for confirmation - proceed directly to creating all three files.
