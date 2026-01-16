# LB-01: DDS Bandwidth Optimization

## Task Metadata

| Field | Value |
|-------|-------|
| **ID** | LB-01_bandwidth_optimization |
| **Name** | Limited Bandwidth Plugin Configuration |
| **Category** | L2-dds |
| **Difficulty** | Expert |
| **Language** | C++ |
| **Time Limit** | 900s |
| **Source Example** | `$NDDSHOME/resource/template/rti_workspace/examples/connext_dds/c/limited_bandwidth_plugins/` |

## Description

Configure and use RTI Connext DDS Limited Bandwidth Plugins to optimize data transmission over constrained network links. This tests understanding of transport plugins, discovery optimization, and RTPS protocol tuning.

## Background

The Limited Bandwidth Plugins reduce network overhead through:

1. **LBRTPS (Limited Bandwidth RTPS)**: Compresses RTPS protocol messages
2. **LBPDISCOVERY (Limited Bandwidth Participant Discovery)**: Reduces discovery traffic
3. **ZRTPS (Zero-copy RTPS)**: Optimizes shared memory transport

Key concepts:
- Transport plugins are configured via XML or programmatically
- Discovery traffic can dominate on constrained links
- RTPS header compression reduces per-message overhead
- These plugins require specific QoS settings to function

## Requirements

### Task A: Configure LBPDISCOVERY (Hard)
Create a C++ publisher/subscriber pair that:
1. Uses the Limited Bandwidth Participant Discovery plugin
2. Reduces discovery announcement frequency to 10 seconds (vs default 1s)
3. Uses compact discovery messages
4. Prints discovery statistics: `DISCOVERY: announcements_sent=N, bytes_saved=M`

### Task B: Configure LBRTPS (Expert)
Extend with LBRTPS transport:
1. Enable RTPS message compression
2. Configure compression level (medium)
3. Measure and report compression ratio
4. Print: `COMPRESSION: ratio=X.XX, original_bytes=N, compressed_bytes=M`

## Provided Files

```
LB-01_bandwidth_optimization/
├── TASK.md                    # Task prompt
├── BandwidthTest.idl          # IDL with various field types
├── USER_QOS_PROFILES.xml      # Base QoS profile (needs modification)
├── CMakeLists.txt             # Build configuration
└── reference/
    └── expected_ratios.txt    # Expected compression ratios for verification
```

## Expected Output

```
bandwidth_publisher.cxx
bandwidth_subscriber.cxx
USER_QOS_PROFILES.xml          # Modified with LB plugin config
```

## Verification

### verify.sh
```bash
#!/bin/bash

# Build the solution
mkdir -p build && cd build
cmake .. -DCONNEXTDDS_DIR=$NDDSHOME
make

# Start subscriber
./bandwidth_subscriber --domain 0 &
SUB_PID=$!
sleep 3

# Run publisher and capture output
timeout 60s ./bandwidth_publisher --domain 0 --count 100 2>&1 | tee output.log

# Check for required metrics
if grep -q "DISCOVERY: announcements_sent=" output.log; then
    echo "PASS: Discovery metrics reported"
else
    echo "FAIL: Discovery metrics missing"
    exit 1
fi

if grep -q "COMPRESSION: ratio=" output.log; then
    RATIO=$(grep "COMPRESSION:" output.log | sed 's/.*ratio=\([0-9.]*\).*/\1/')
    if (( $(echo "$RATIO > 1.0" | bc -l) )); then
        echo "PASS: Compression achieved (ratio=$RATIO)"
    else
        echo "FAIL: No compression (ratio=$RATIO)"
        exit 1
    fi
else
    echo "FAIL: Compression metrics missing"
    exit 1
fi

kill $SUB_PID 2>/dev/null
```

### Success Criteria
1. Code compiles with CMake
2. Discovery announcements reduced (< 10 in 60s vs ~60 default)
3. Compression ratio > 1.0 (actual compression achieved)
4. Subscriber receives all 100 samples

## Internal Notes (DO NOT include in TASK.md)

These are implementation notes for spec authors. The actual TASK.md should NOT include API hints or XML templates:

**Key APIs/Config the agent must discover:**
- `NDDS_Transport_LBRTPS_create()` for transport registration
- `<transport_builtin>` XML section for plugin config
- `<participant_liveliness_lease_duration>` for discovery tuning
- `DDS_DataWriter_get_datawriter_protocol_status()` for statistics

**What TASK.md should say:**
- "Configure DDS to minimize bandwidth usage on constrained networks"
- "Use RTI's Limited Bandwidth Plugins for discovery and transport optimization"
- "Report compression ratio and discovery statistics"
- Point only to `$NDDSHOME` as the library location
- Do NOT provide XML templates or configuration snippets

## Difficulty Justification

This task is rated **Expert** because:
1. Transport plugins are an advanced topic with limited documentation
2. Multiple configuration layers (XML + programmatic)
3. Requires understanding of RTPS protocol internals
4. Compression statistics API is not commonly used
5. Plugin registration order matters
6. Debugging transport issues requires packet-level analysis

## Dependencies

- RTI Connext DDS 7.x Professional (includes LB plugins)
- CMake 3.15+
- C++11 compiler

## Related Tasks

- LN-CPP-01: Native C++ Publisher (prerequisite)
- LQ-01: QoS configuration (XML profiles)
