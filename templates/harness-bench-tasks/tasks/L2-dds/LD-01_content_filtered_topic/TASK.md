# Help! I need to filter DDS data efficiently

I have a publisher sending sensor data from 100 sensors, and I only care about a few of them - specifically sensors with ID > 50 that have values > 75.

Right now I'm filtering in my application code, but my colleague said DDS can filter at the network level using something called "ContentFilteredTopic"? That sounds way more efficient.

## What I have

A working `publisher.py` is already in this directory - **DO NOT MODIFY IT**. Study it to understand:
- The exact data type definition (copy it EXACTLY)
- The QoS settings (your reader QoS must be compatible)
- The topic name and domain

## What I need

A `subscriber.py` that:
- Subscribes to the "SensorReadings" topic  
- Uses DDS content filtering (ContentFilteredTopic, not application filtering)
- Only receives samples where `id > 50` AND `value > 75.0`
- Outputs received samples as JSONL
- Uses async pattern (WaitSet), not polling

## Data Type

Look at publisher.py for the exact type definition. It's a SensorReading with:
- id (integer)
- value (float64)  
- timestamp (float64)

## Output

JSONL to stdout:
```
{"id": 51, "value": 80.5, "timestamp": 1234567890.123}
```

## What I know

- RTI Connext DDS Python API (`rti.connextdds`)
- DDS has SQL-like filter expressions
- ContentFilteredTopic wraps a regular topic with a filter

## API Hints

For DynamicData topics, use `dds.DynamicData.ContentFilteredTopic`:
```python
cft = dds.DynamicData.ContentFilteredTopic(
    topic,                    # Base DynamicData.Topic
    "FilteredTopicName",      # Name for filtered topic
    dds.Filter("expression")  # SQL filter wrapped in dds.Filter()
)
```

**QoS Compatibility:** Look at publisher.py's QoS settings. Your DataReader QoS must be compatible:
- RELIABLE writer requires RELIABLE reader (or BEST_EFFORT if writer allows)
- TRANSIENT_LOCAL durability requires matching reader durability to receive historical data

## CRITICAL: DDS Interoperability Requirements

**Topic name must match EXACTLY.** Use `"SensorReadings"` exactly as shown - not `"SensorReadingsTopic"` or any variation. DDS only communicates when topic names match character-for-character.

**Type must match the publisher.** Your subscriber's type definition must EXACTLY match what's in `publisher.py`:
- Same type name
- Same field names and types
- Same approach (DynamicData vs IDL) - check publisher.py to see which it uses

**DynamicData and IDL may NOT interoperate.** If the publisher uses DynamicData, your subscriber must also use DynamicData. If it uses `@idl.struct`, you must use the same.

## Development approach

**Test early, test often!** Run `python test_subscriber.py` after changes.

You can also test manually:
1. Start your subscriber: `python subscriber.py`
2. In another terminal, run the publisher: `python publisher.py`
3. Your subscriber should only print samples matching: id > 50 AND value > 75.0

## Help me!

Can you create subscriber.py? I want to use the proper DDS way, not filter in my code.
