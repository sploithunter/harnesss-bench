# Help me write a DDS subscriber

I need to create a subscriber that receives "HelloWorld" messages and prints them.

## What I need

A `subscriber.py` file that:
- Subscribes to the "HelloWorld" topic on domain 0
- The topic has two fields: `message` (string) and `count` (integer)
- Prints each received sample as JSON, one per line (JSONL format)
- Accepts `--count N` to receive N samples and `--timeout T` for max wait time
- Should NOT use busy-waiting/polling - use proper async DDS patterns

## Output format

Each sample should be printed as a single JSON line:
```
{"message": "Hello World 1", "count": 1}
{"message": "Hello World 2", "count": 2}
```

## What I know

- Using RTI Connext DDS Python API (`rti.connextdds`)
- I've heard DDS has WaitSet and Listener patterns for async data reception
- There's a `dds-spy-wrapper` tool in this project for testing - it can verify if data is on the wire

## API Hints

For DynamicData (runtime types without IDL), use these patterns:
```python
# Create the type
hello_type = dds.StructType("HelloWorld")
hello_type.add_member(dds.Member("message", dds.StringType(256)))
hello_type.add_member(dds.Member("count", dds.Int32Type()))

# Create topic with DynamicData.Topic (NOT plain dds.Topic)
topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)

# Create reader with DynamicData.DataReader
reader = dds.DynamicData.DataReader(subscriber, topic)
```

**Important:** Use `dds.DynamicData.Topic` and `dds.DynamicData.DataReader` for runtime types. Plain `dds.Topic` is for IDL-generated types.

## CRITICAL: DDS Interoperability Requirements

**Topic names must match EXACTLY.** The topic name must be `"HelloWorld"` - not `"HelloWorldTopic"`, not `"hello_world"`, exactly `"HelloWorld"`. DDS publishers and subscribers only communicate if their topic names match character-for-character.

**Type compatibility matters.** For DDS communication to work:
- The type name must match (e.g., `"HelloWorld"`)
- The field names and types must match exactly
- DynamicData publishers can communicate with DynamicData subscribers
- IDL-based (`@idl.struct`) publishers can communicate with IDL-based subscribers
- DynamicData and IDL approaches may NOT interoperate with each other

## Development approach

**Test early, test often!** Run `python test_subscriber.py` after each change.

## Create subscriber.py

Please write the complete subscriber. I'll test it with the reference publisher.
