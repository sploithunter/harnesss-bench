# LP-01: Persistence Service State Recovery

## Task Metadata

| Field | Value |
|-------|-------|
| **ID** | LP-01_persistence_recovery |
| **Name** | DDS Persistence Service - State Recovery |
| **Category** | L2-dds |
| **Difficulty** | Hard |
| **Language** | C |
| **Time Limit** | 600s |
| **Source Example** | `$NDDSHOME/resource/template/rti_workspace/examples/persistence_service/c/hello_world_persistence/` |

## Description

Create a DDS application that leverages RTI Persistence Service for durable data storage and recovery. The application must correctly recover state after restart, demonstrating understanding of TRANSIENT and PERSISTENT durability.

## Background

RTI Persistence Service provides:
- **Durable storage**: Data survives participant/system restarts
- **Historical data**: Late-joining subscribers receive past samples
- **State recovery**: Applications can recover their last known state

Key QoS settings:
- `DURABILITY`: TRANSIENT_LOCAL, TRANSIENT, or PERSISTENT
- `HISTORY`: KEEP_LAST or KEEP_ALL with depth
- `RELIABILITY`: Must be RELIABLE for durability guarantees

Persistence Service acts as a "virtual DataWriter" that:
1. Subscribes to topics with TRANSIENT/PERSISTENT durability
2. Stores samples to persistent storage (file/database)
3. Republishes to late-joining subscribers

## Requirements

### Task A: TRANSIENT Recovery (Moderate)
Create a C publisher and subscriber where:
1. Publisher writes 10 samples with TRANSIENT durability
2. Publisher exits
3. Persistence Service stores the samples
4. Subscriber starts (late joiner)
5. Subscriber receives all 10 historical samples
6. Print: `RECOVERED: sample_count=10`

### Task B: Application State Recovery (Hard)
Extend to support application checkpoint/recovery:
1. Publisher maintains a counter (starts at 0 or recovered value)
2. On startup, query Persistence Service for last checkpoint
3. Resume counting from recovered value
4. Write checkpoints every 5 samples
5. Print: `CHECKPOINT: value=N` and `RECOVERED_FROM: value=M`

## Provided Files

```
LP-01_persistence_recovery/
├── TASK.md                    # Task prompt
├── StateData.idl              # IDL with checkpoint type
├── USER_QOS_PROFILES.xml      # Durability QoS profiles
├── persistence_service.xml    # Persistence Service configuration
├── CMakeLists.txt             # Build configuration
└── reference/
    └── verify_recovery.sh     # Recovery test script
```

## IDL Definition

```idl
struct Checkpoint {
    @key string application_id;
    long sequence_number;
    long long timestamp;
    string state_data;  // JSON or serialized application state
};

struct SensorReading {
    @key long sensor_id;
    float value;
    long long timestamp;
};
```

## Expected Output

```
state_publisher.c
state_subscriber.c
```

## Verification

### verify.sh
```bash
#!/bin/bash

# Start Persistence Service
$NDDSHOME/bin/rtipersistenceservice \
    -cfgFile persistence_service.xml \
    -cfgName StateRecovery &
PS_PID=$!
sleep 3

# Phase 1: Initial publish
echo "=== Phase 1: Initial Publish ==="
./state_publisher --domain 0 --count 10 --app-id "test_app"
sleep 2

# Phase 2: Late-joining subscriber
echo "=== Phase 2: Late Joiner ==="
timeout 10s ./state_subscriber --domain 0 --app-id "test_app" 2>&1 | tee phase2.log

if grep -q "RECOVERED: sample_count=10" phase2.log; then
    echo "PASS: Phase 2 - All samples recovered"
else
    echo "FAIL: Phase 2 - Recovery failed"
    kill $PS_PID
    exit 1
fi

# Phase 3: Checkpoint recovery
echo "=== Phase 3: Checkpoint Recovery ==="
./state_publisher --domain 0 --count 5 --app-id "test_app" --checkpoint
# Simulate crash
./state_publisher --domain 0 --count 5 --app-id "test_app" --recover 2>&1 | tee phase3.log

if grep -q "RECOVERED_FROM: value=" phase3.log; then
    RECOVERED_VAL=$(grep "RECOVERED_FROM" phase3.log | sed 's/.*value=\([0-9]*\).*/\1/')
    if [ "$RECOVERED_VAL" -eq 5 ]; then
        echo "PASS: Phase 3 - Checkpoint recovery correct (value=$RECOVERED_VAL)"
    else
        echo "FAIL: Phase 3 - Wrong recovery value (expected 5, got $RECOVERED_VAL)"
        exit 1
    fi
else
    echo "FAIL: Phase 3 - No recovery message"
    exit 1
fi

kill $PS_PID
echo "All tests passed!"
```

### Success Criteria
1. Publisher compiles and writes TRANSIENT samples
2. Subscriber receives historical samples from Persistence Service
3. Checkpoint mechanism stores application state
4. Recovery correctly restores last checkpoint value

## Internal Notes (DO NOT include in TASK.md)

These are implementation notes for spec authors. The actual TASK.md should NOT include API hints or QoS templates:

**Key concepts the agent must discover:**
- TRANSIENT durability requires RELIABLE reliability
- DURABILITY_SERVICE QoS for history configuration
- Persistence Service as "virtual DataWriter"
- Keyed topics for checkpoint management
- DataReader `read()` on startup for recovery

**What TASK.md should say:**
- "Create a publisher/subscriber pair with durable data storage"
- "Late-joining subscribers must receive historical samples"
- "Implement application checkpoint and recovery after restart"
- Point only to `$NDDSHOME` as the library location
- Provide data model as XML (not IDL)
- Do NOT provide QoS configuration templates

## Difficulty Justification

This task is rated **Hard** because:
1. Requires understanding of DDS durability semantics
2. Persistence Service must be configured correctly
3. Timing between publisher exit and subscriber join matters
4. Checkpoint/recovery pattern is not a standard DDS example
5. Debugging requires understanding of Persistence Service logs
6. QoS compatibility between entities is critical

## Dependencies

- RTI Connext DDS 7.x with Persistence Service
- C compiler
- Persistence Service configuration file

## Related Tasks

- LQ-01: Late Joiner Durability (simpler durability test)
- LD-01: Content Filtered Topic (QoS configuration)
