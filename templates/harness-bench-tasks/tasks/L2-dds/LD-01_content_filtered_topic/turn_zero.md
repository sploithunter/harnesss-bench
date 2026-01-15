# Task: Create Content Filtered Topic Subscriber

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- A working `publisher.py` is provided - **read it first** to understand the type and topic
- Run `python test_subscriber.py` to verify your solution

## The Scenario

A publisher (see `publisher.py`) is sending sensor readings to topic "SensorReadings". Each reading contains:
- `id`: integer (sensor ID)
- `value`: float64 (sensor value)
- `timestamp`: float64 (unix timestamp)

You only care about readings where **id > 50 AND value > 75.0**.

Currently someone suggested filtering in application code, but your colleague mentioned DDS can filter at the network/middleware level using something called a "ContentFilteredTopic" - which is more efficient because unwanted data never even reaches your application.

## Your Task

Create `subscriber.py` that:

1. Subscribes to the "SensorReadings" topic
2. Uses **DDS content filtering** (ContentFilteredTopic) - NOT application-level filtering
3. Filter condition: `id > 50 AND value > 75.0`
4. Outputs received samples as JSONL to stdout
5. Uses async pattern (WaitSet), NOT polling
6. Accepts `--count`, `--timeout`, `--domain` arguments (optional but nice to have)

## Output Format

JSONL to stdout:
```
{"id": 51, "value": 80.5, "timestamp": 1234567890.123}
{"id": 72, "value": 92.1, "timestamp": 1234567890.456}
```

## Hints

- **Read publisher.py first** - it shows the exact type definition you need to match
- DDS filter expressions use SQL-like syntax
- ContentFilteredTopic wraps a regular topic with a filter expression
- The DataReader subscribes to the filtered topic, not the base topic
- Use RELIABLE + TRANSIENT_LOCAL QoS for durability

## Test Your Solution

Run: `python test_subscriber.py`

You can also test manually:
1. Start subscriber: `python subscriber.py`
2. In another terminal: `python publisher.py`
3. Subscriber should only print samples where id > 50 AND value > 75.0
