# SOLUTION - Development/Testing Only
# This file should NEVER be visible to models during actual benchmarking

## The Fix

Change BOTH publisher.py AND subscriber.py QoS. All three settings are required:
- TRANSIENT_LOCAL durability (caches data for late joiners)
- RELIABLE reliability (enables resend mechanism - critical!)
- KEEP_ALL history (stores all samples, not just the last one)

## publisher.py Changes

```python
writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
```

Publisher must stay alive while late joiners connect (sleep or wait_for_acknowledgments).

## subscriber.py Changes

```python
reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
reader_qos.history.kind = dds.HistoryKind.KEEP_ALL
```

## Why This Works

1. **TRANSIENT_LOCAL**: Writer caches samples; reader requests cached data on join
2. **RELIABLE**: Enables the resend mechanism - without this, late joiners get nothing!
3. **KEEP_ALL**: Stores all samples (default KEEP_LAST with depth=1 only keeps one)

Note: The publisher must remain alive for late joiners to receive data.
DDS has no intermediate broker - the writer serves cached data directly.


