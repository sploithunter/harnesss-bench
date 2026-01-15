# Help me write a DDS Hello World publisher

I'm new to RTI Connext DDS and need to create a simple publisher in Python.

## What I need

A `publisher.py` file that:
- Creates a "HelloWorld" topic with two fields: `message` (string, max 256 chars) and `count` (integer)
- Publishes 10 samples at 2 Hz (every 0.5 seconds)
- Each sample should have `message` = "Hello World 1", "Hello World 2", etc. and `count` = 1, 2, etc.
- Uses domain 85

## What I know

- I have RTI Connext DDS 7.x installed with the Python API (`rti.connextdds`)
- I've heard about DynamicData for creating types at runtime without IDL files
- The project has a tool called `dds-spy-wrapper` that can subscribe to any topic without needing type definitions - good for testing

## API Hints

For DynamicData (runtime types without IDL), use these patterns:
```python
# Create the type
hello_type = dds.StructType("HelloWorld")
hello_type.add_member(dds.Member("message", dds.StringType(256)))
hello_type.add_member(dds.Member("count", dds.Int32Type()))

# Create topic with DynamicData.Topic (NOT plain dds.Topic)
topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)

# Create writer with DynamicData.DataWriter
writer = dds.DynamicData.DataWriter(publisher, topic)

# Create and write samples
sample = dds.DynamicData(hello_type)
sample["message"] = "Hello World 1"
sample["count"] = 1
writer.write(sample)
```

**Important:** Use `dds.DynamicData.Topic` and `dds.DynamicData.DataWriter` for runtime types.

## CRITICAL: DDS Interoperability Requirements

**Topic names must match EXACTLY.** The topic name must be `"HelloWorld"` - not `"HelloWorldTopic"`, not `"hello_world"`, exactly `"HelloWorld"`. DDS publishers and subscribers only communicate if their topic names match character-for-character.

**Type compatibility matters.** For DDS communication to work:
- The type name must match (e.g., `"HelloWorld"`)
- The field names and types must match exactly
- DynamicData publishers can communicate with DynamicData subscribers
- IDL-based (`@idl.struct`) publishers can communicate with IDL-based subscribers
- DynamicData and IDL approaches may NOT interoperate with each other

## Development approach

**Test early, test often!** I want to verify my publisher works before moving on. Run `python test_publisher.py` after making changes.

## Help me get started!

Can you create the complete `publisher.py`? I'll test it with the spy wrapper to make sure it's working.
