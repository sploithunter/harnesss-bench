# LR-02: Routing Service Custom Adapter

## Task Metadata

| Field | Value |
|-------|-------|
| **ID** | LR-02_routing_service_adapter |
| **Name** | Custom Routing Service Adapter |
| **Category** | L2-dds |
| **Difficulty** | Hard |
| **Language** | C++ |
| **Time Limit** | 900s |
| **Source Example** | `$NDDSHOME/resource/template/rti_workspace/examples/routing_service/adapters/` |

## Description

Create a custom RTI Routing Service adapter that bridges data between a file-based source and DDS. This tests understanding of the Routing Service Plugin API, adapter lifecycle, and data transformation.

## Background

RTI Routing Service can route data between different:
- DDS domains
- DDS and non-DDS systems (via adapters)
- Topics with different types (via transformations)

Custom adapters implement:
- `RTI_RoutingServiceAdapterPlugin` - Plugin registration
- `RTI_RoutingServiceConnection` - Represents a connection to external system
- `RTI_RoutingServiceStreamReader` - Reads data from external source
- `RTI_RoutingServiceStreamWriter` - Writes data to external sink

## Requirements

### Task A: File Reader Adapter (Hard)
Create a Routing Service adapter that:
1. Reads JSON records from a file
2. Converts each JSON record to DDS DynamicData
3. Publishes to a DDS topic via Routing Service
4. Handles file polling (check for new lines every 1 second)

JSON format:
```json
{"sensor_id": 1, "temperature": 25.5, "timestamp": 1234567890}
```

### Task B: Bidirectional Adapter (Expert - Optional)
Extend to also write:
1. Subscribe to a DDS command topic
2. Write commands to an output file
3. Handle graceful shutdown

## Provided Files

```
LR-02_routing_service_adapter/
├── TASK.md                    # Task prompt
├── SensorData.idl             # IDL type definition
├── CMakeLists.txt             # Build configuration
├── routing_service.xml        # Routing Service configuration (incomplete)
├── test_data/
│   └── sensor_input.json      # Test input file
└── reference/
    └── expected_output.txt    # Expected DDS samples
```

## Expected Output

```
FileAdapter.hpp                # Adapter header
FileAdapter.cxx                # Adapter implementation
FileStreamReader.hpp           # Stream reader header
FileStreamReader.cxx           # Stream reader implementation
routing_service.xml            # Completed RS configuration
```

## Verification

### verify.sh
```bash
#!/bin/bash

# Build the adapter
mkdir -p build && cd build
cmake .. -DCONNEXTDDS_DIR=$NDDSHOME -DRTICODEGEN_DIR=$NDDSHOME/bin
make

# Start a DDS subscriber to capture output
./reference_subscriber --domain 0 --topic "SensorTopic" &
SUB_PID=$!
sleep 2

# Start Routing Service with the custom adapter
$NDDSHOME/bin/rtiroutingservice \
    -cfgFile ../routing_service.xml \
    -cfgName FileToDD &
RS_PID=$!
sleep 5

# Check that samples were received
if [ -f subscriber_output.log ]; then
    SAMPLE_COUNT=$(grep -c "sensor_id" subscriber_output.log)
    if [ "$SAMPLE_COUNT" -ge 3 ]; then
        echo "PASS: Received $SAMPLE_COUNT samples"
    else
        echo "FAIL: Only received $SAMPLE_COUNT samples (expected >= 3)"
        exit 1
    fi
else
    echo "FAIL: No output received"
    exit 1
fi

kill $SUB_PID $RS_PID 2>/dev/null
```

### Success Criteria
1. Adapter compiles as shared library (.so/.dylib)
2. Routing Service loads the adapter without errors
3. At least 3 JSON records are converted and published to DDS
4. Data types match (sensor_id, temperature, timestamp)

## Internal Notes (DO NOT include in TASK.md)

These are implementation notes for spec authors. The actual TASK.md should NOT include API hints or XML templates:

**Key APIs the agent must discover:**
- `RTI_RoutingServiceAdapterPlugin` interface
- `RTI_RoutingServiceConnection` lifecycle
- `RTI_RoutingServiceStreamReader` / `StreamWriter`
- `DDS_DynamicData` for type conversion
- Plugin library export function conventions

**What TASK.md should say:**
- "Create a Routing Service adapter that bridges JSON files to DDS"
- "The adapter must read JSON records and publish them as DDS samples"
- "Configure Routing Service to load your custom adapter"
- Point only to `$NDDSHOME` as the library location
- Do NOT provide XML configuration templates

## Difficulty Justification

This task is rated **Hard** because:
1. Routing Service Plugin API has many required callbacks
2. DynamicData manipulation for type conversion
3. Memory management for sample lifecycle
4. XML configuration must match code exactly
5. Debugging requires Routing Service logs
6. Less common use case with fewer online examples

## Dependencies

- RTI Connext DDS 7.x with Routing Service
- CMake 3.15+
- C++11 compiler
- JSON parsing library (nlohmann/json or similar)

## Related Tasks

- LN-CPP-01: Native C++ Publisher (DynamicData basics)
- LD-03: rtiddsgen workflow (type generation)
