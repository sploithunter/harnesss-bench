# Task: Build Binary Protocol to DDS Bridge

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- `protocol.py` is provided in the workspace - read it to understand the binary protocol
- Run `python test_bridge.py` to verify your solution

## The Scenario

You have a legacy system that speaks a simple binary protocol, and you need to bridge it to DDS. Then you need to go from DDS back to binary (for a different legacy system).

## The Binary Protocol

Check `protocol.py` for the full implementation. The protocol uses:
- 4 bytes: message length (big-endian uint32)
- N bytes: JSON payload

Three message types:
- **Heartbeat**: seq (int), timestamp (float)
- **Position**: id (int), x (float), y (float), z (float)
- **Command**: id (int), action (string), params (dict)

The file provides `encode_message()`, `decode_message()`, and dataclasses for each message type.

## Files to Create

### 1. inbound_adapter.py (Binary → DDS)

- Read binary messages from a file (`--input` argument)
- Publish each message to the appropriate DDS topic
- Use separate topics for each message type: "Heartbeat", "Position", "Command"

### 2. outbound_adapter.py (DDS → Binary)

- Subscribe to all three DDS topics
- Write received messages to a binary file (`--output` argument)
- Accept `--count N` for expected message count, `--timeout T` for max wait
- **Must use async pattern (WaitSet)** - NOT polling!

## Requirements

- Both adapters must use RELIABLE + TRANSIENT_LOCAL QoS (data must survive late joiners)
- Both adapters run independently (could start in any order)
- The Command message has a `params` dict - you'll need to handle this appropriately for DDS

## Test Your Solution

Run: `python test_bridge.py`

This runs both adapters and verifies the binary output matches the input.
