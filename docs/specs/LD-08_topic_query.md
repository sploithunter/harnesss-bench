# LD-08: Topic Query Historical Data Retrieval

## Task Metadata

| Field | Value |
|-------|-------|
| **ID** | LD-08_topic_query |
| **Name** | Historical Data Retrieval with Topic Queries |
| **Category** | L2-dds |
| **Difficulty** | Hard |
| **Language** | C |
| **Time Limit** | 600s |
| **Source Example** | `$NDDSHOME/resource/template/rti_workspace/examples/connext_dds/c/hello_world_topic_query/` |

## Description

Create a DDS subscriber that uses Topic Queries to retrieve historical data from a publisher that started before the subscriber. This tests the ability to discover and use advanced DDS APIs for historical data access.

## Philosophy

This task tests the AI's ability to:
1. Discover the Topic Query API from documentation/examples
2. Understand the relationship between durability, history, and topic queries
3. Implement a working solution without step-by-step guidance

**Minimal hints are provided.** The AI must figure out the correct APIs.

## Requirements

Create a C subscriber application that:

1. Connects to domain 0
2. Creates a Topic Query to request historical samples
3. Receives both historical (queried) and live samples
4. Distinguishes between historical and live samples in output
5. Prints sample count summaries

### Output Format
```
HISTORICAL: id=<id> message="<msg>" source_guid=<guid>
LIVE: id=<id> message="<msg>"
SUMMARY: historical_count=<N> live_count=<M>
```

## Provided Files

The task provides minimal scaffolding:

```
LD-08_topic_query/
├── TASK.md              # Task description (see below)
├── data_model.xml       # Data type in XML format (not IDL!)
└── verify.sh            # Verification script
```

### data_model.xml
```xml
<!--
  The subscriber must handle this data type.
  Convert to appropriate format for your implementation.
-->
<types>
  <struct name="SensorReading">
    <member name="id" type="int32" key="true"/>
    <member name="message" type="string" stringMaxLength="256"/>
  </struct>
</types>
```

### TASK.md (What the AI sees)
```markdown
# Topic Query Historical Data Retrieval

## Objective
Create a C subscriber that retrieves historical data using DDS Topic Queries.

## Scenario
A publisher has been running and has written 20 samples to a topic called
"SensorTopic" with TRANSIENT_LOCAL durability. Your subscriber starts late
and needs to retrieve those historical samples.

## Requirements
1. Write a C subscriber: `topic_query_subscriber.c`
2. The subscriber must retrieve historical samples using Topic Queries
3. Print each sample, indicating whether it's HISTORICAL or LIVE
4. Print a final summary with counts

## Data Type
See `data_model.xml` for the data structure. You'll need to convert this
to a usable format for your C application.

## Environment
- RTI Connext DDS is installed at $NDDSHOME
- Domain ID: 0
- Topic: "SensorTopic"

## Verification
Your subscriber will be tested against a reference publisher that:
1. Publishes 20 historical samples (before your subscriber starts)
2. Then publishes 5 live samples (after your subscriber joins)

Expected output should show 20 HISTORICAL and 5 LIVE samples.

## Constraints
- Use C language (not C++ or Python)
- Must compile with standard RTI build process
- Time limit: 600 seconds
```

## Verification

### verify.sh
```bash
#!/bin/bash
set -e

# Convert XML to IDL if the agent didn't
if [ ! -f SensorReading.idl ]; then
    if [ -f topic_query_subscriber.c ]; then
        # Agent may have created their own IDL
        :
    else
        echo "FAIL: No subscriber implementation found"
        exit 1
    fi
fi

# Build agent's solution
if [ -f Makefile ] || [ -f makefile_* ]; then
    make -f makefile_* 2>&1 || make 2>&1
elif [ -f CMakeLists.txt ]; then
    mkdir -p build && cd build && cmake .. && make && cd ..
else
    # Try rtiddsgen + manual compile
    $NDDSHOME/bin/rtiddsgen -language C -example $(uname -m)* SensorReading.idl 2>/dev/null || true
    gcc -I$NDDSHOME/include -I$NDDSHOME/include/ndds \
        -L$NDDSHOME/lib/* -lnddsc -lnddscore \
        topic_query_subscriber.c -o topic_query_subscriber 2>&1
fi

# Start reference publisher with historical data
./ref_topic_query_publisher --domain 0 --historical 20 &
PUB_PID=$!
sleep 5  # Let publisher write historical samples

# Run agent's subscriber
timeout 30s ./topic_query_subscriber 2>&1 | tee output.log &
SUB_PID=$!
sleep 3

# Publisher sends live samples
./ref_topic_query_publisher --domain 0 --live 5 --no-historical
sleep 5

wait $SUB_PID 2>/dev/null || true
kill $PUB_PID 2>/dev/null || true

# Verify output
HISTORICAL=$(grep -c "^HISTORICAL:" output.log || echo 0)
LIVE=$(grep -c "^LIVE:" output.log || echo 0)

echo "Results: historical=$HISTORICAL live=$LIVE"

if [ "$HISTORICAL" -ge 15 ] && [ "$LIVE" -ge 3 ]; then
    echo "PASS: Retrieved historical and live samples"
    exit 0
else
    echo "FAIL: Expected ~20 historical and ~5 live samples"
    exit 1
fi
```

### Success Criteria
1. Code compiles (any reasonable build method)
2. Subscriber distinguishes historical from live samples
3. At least 75% of historical samples retrieved (15/20)
4. At least 60% of live samples received (3/5)
5. Output format matches specification

## What Makes This Hard

1. **API Discovery**: Topic Query API is not commonly used; AI must find it
2. **Format Conversion**: Data model given as XML, not IDL
3. **QoS Configuration**: Must figure out correct durability/history settings
4. **Sample Classification**: Must use sample info to distinguish historical vs live
5. **No Code Templates**: No starter code provided
6. **Build System**: Must create build files from scratch

## Anti-Patterns (What We DON'T Want)

The following would make the task too easy and should NOT be included:
- IDL file (they must convert from XML or create their own)
- Makefile or CMakeLists.txt
- QoS XML with correct settings
- Code snippets showing Topic Query API usage
- Specific function names to call

## Difficulty Justification

This task is rated **Hard** because:
1. Topic Queries are an advanced, rarely-used feature
2. No scaffolding code provided
3. Data format conversion required (XML → IDL)
4. Must understand durability + topic query interaction
5. Sample metadata access needed for classification

## Dependencies

- RTI Connext DDS 7.x
- C compiler (gcc/clang)
- Reference publisher (in harness-bench-eval)

## Related Tasks

- LQ-01: Late Joiner Durability (simpler durability)
- LD-07: Discovery GUID Mining (sample info access)
