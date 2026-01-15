# Help! Build a binary protocol to DDS bridge

I have a legacy system that speaks a simple binary protocol, and I need to bridge it to DDS. Then I need to go back from DDS to binary (for a different legacy system).

## The Binary Protocol

The protocol is defined in `protocol.py`:
- 4 bytes: message length (big-endian uint32)  
- N bytes: JSON payload

Message types:
- **Heartbeat**: `{"type": "heartbeat", "seq": int, "timestamp": float}`
- **Position**: `{"type": "position", "id": int, "x": float, "y": float, "z": float}`
- **Command**: `{"type": "command", "id": int, "action": str, "params": dict}`

`protocol.py` provides `encode_message()` and `decode_message()` functions.

## What I need

### 1. inbound_adapter.py (Binary → DDS)
- Read binary messages from a file (`--input`)
- Publish each message to the appropriate DDS topic
- Topics: "Heartbeat", "Position", "Command"

### 2. outbound_adapter.py (DDS → Binary)
- Subscribe to the DDS topics
- Write received messages to binary file (`--output`)
- Use async pattern (WaitSet), NOT polling!

## DDS Types

Create DynamicData types that match the protocol:

```python
# Heartbeat
heartbeat_type = dds.StructType("Heartbeat")
heartbeat_type.add_member(dds.Member("seq", dds.Int32Type()))
heartbeat_type.add_member(dds.Member("timestamp", dds.Float64Type()))

# Position  
position_type = dds.StructType("Position")
position_type.add_member(dds.Member("id", dds.Int32Type()))
position_type.add_member(dds.Member("x", dds.Float64Type()))
# etc...

# Command (params stored as JSON string)
command_type = dds.StructType("Command")
command_type.add_member(dds.Member("id", dds.Int32Type()))
command_type.add_member(dds.Member("action", dds.StringType(256)))
command_type.add_member(dds.Member("params_json", dds.StringType(1024)))
```

## API Hints

For DynamicData topics, use these patterns:
```python
# Create topic with DynamicData.Topic (NOT plain dds.Topic)
topic = dds.DynamicData.Topic(participant, "TopicName", struct_type)

# Create writer/reader with DynamicData variants
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
```

**Important:** Use `dds.DynamicData.Topic`, `dds.DynamicData.DataWriter`, and `dds.DynamicData.DataReader` for runtime types.

## CRITICAL: DDS Interoperability Requirements

**Topic names must match EXACTLY.** Use exactly `"Heartbeat"`, `"Position"`, `"Command"` - not variations like `"HeartbeatTopic"`. DDS only communicates when topic names match character-for-character.

**Type structure must match EXACTLY.** The type definitions above are required - use the exact field names and types shown. Both inbound and outbound adapters must use identical type definitions.

**Use DynamicData consistently.** Both adapters must use DynamicData (as shown above). Do NOT use `@idl.struct` decorators - they may not interoperate with DynamicData.

## Important

- Use RELIABLE + TRANSIENT_LOCAL QoS (data must survive late joiners)
- Outbound adapter MUST use WaitSet (no polling!)
- Both adapters run independently (could start in any order)

## Testing

```bash
# Generate test data
python -c "from protocol import *; open('test.bin','wb').write(b''.join(encode_message(m) for m in generate_test_messages(10)))"

# Run outbound first (subscriber)
python outbound_adapter.py --output received.bin --count 10 --timeout 30 &

# Then inbound (publisher)  
python inbound_adapter.py --input test.bin

# Compare
diff test.bin received.bin && echo "SUCCESS!"
```

## Development approach

**Test early, test often!** Run `python test_bridge.py` after changes.

## Files to create

1. `inbound_adapter.py` - Binary → DDS
2. `outbound_adapter.py` - DDS → Binary

The `protocol.py` file is already provided.


