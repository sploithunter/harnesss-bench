# Task: RTI DDS Gen Workflow - Generated Types

## Environment
- RTI Connext DDS 7.x with Python API installed
- `$NDDSHOME` environment variable is set to the RTI installation
- `rtiddsgen` tool is available at `$NDDSHOME/bin/rtiddsgen`
- Run `python test_workflow.py` to verify your solution

## The Scenario

So far you've used **DynamicData** - defining types at runtime. But production systems often use **Generated Types** - types compiled from IDL files. This gives you:
- Type safety at compile time
- Better performance
- IDE autocomplete
- Standard across all DDS implementations

## Your Task

Complete the rtiddsgen workflow:

1. **Write an IDL file** (`HelloWorld.idl`) defining a struct with:
   - `message`: string (max 256 chars)
   - `count`: 32-bit integer

2. **Run rtiddsgen** to generate Python code from the IDL

3. **Create publisher.py** using the generated types (not DynamicData)

4. **Create subscriber.py** using the generated types (not DynamicData)

5. Both should communicate successfully, exchanging 10 samples

## IDL Basics

IDL (Interface Definition Language) is the standard way to define DDS types:
- `string<N>` = bounded string of max N chars
- `long` = 32-bit signed integer
- `double` = 64-bit float

## Running rtiddsgen

```bash
$NDDSHOME/bin/rtiddsgen -language python -d . HelloWorld.idl
```

This generates `HelloWorld.py` which you can import.

## Key Differences from DynamicData

With generated types:
- Use `dds.Topic(participant, "HelloWorld", HelloWorld)` - pass the type class directly
- Use `dds.DataWriter(publisher, topic)` - NOT `dds.DynamicData.DataWriter`
- Instantiate samples with `sample = HelloWorld()` - NOT `dds.DynamicData(type)`
- Access fields via attributes: `sample.message` - NOT `sample["message"]`

## CRITICAL: Subscriber Output Format

The test harness expects subscriber output as **JSON lines**. Each received sample must be printed as:

```python
import json

# For each received sample:
output = {"message": sample.data.message, "count": sample.data.count}
print(json.dumps(output))
```

Example output the test expects:
```
{"message": "Hello World 1", "count": 1}
{"message": "Hello World 2", "count": 2}
...
```

**Do NOT use print statements like `print(f"Received: {sample.data.message}")` - the test counts lines starting with `{`**

## Subscriber Pattern

Use a WaitSet with ReadCondition for blocking waits:

```python
waitset = dds.WaitSet()
condition = dds.ReadCondition(reader, dds.DataState.any_data)
waitset.attach_condition(condition)

while received < 10:
    active = waitset.wait(dds.Duration.from_seconds(5.0))
    if condition in active:
        for sample in reader.take():
            if sample.info.valid:
                # Output as JSON
                print(json.dumps({"message": sample.data.message, "count": sample.data.count}))
                received += 1
```

## Test Your Solution

1. Generate types from IDL
2. Verify the import works: `python -c "from HelloWorld import HelloWorld"`
3. Run: `python test_workflow.py`
