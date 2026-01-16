# Debug: Publisher and Subscriber Not Communicating

I have a temperature monitoring system with a publisher and subscriber. They **should** be communicating, but the subscriber receives **ZERO** samples. Both are on the same domain, using the same topic name and type. I've confirmed they both start correctly.

## The symptom

```
Publisher output:
  Published: reading_num=1, celsius=22.6
  Published: reading_num=2, celsius=22.7
  ...
  Published 10 samples

Subscriber output:
  Waiting for temperature readings...
  (nothing received)
  Received 0/10 readings
```

The subscriber just sits there waiting. No data arrives. No errors. Nothing.

## What I've already checked

- Both processes are on domain 0 ✓
- Topic name "TemperatureReading" matches ✓
- Type definition is identical in both files ✓
- DDS discovery is working (other apps on same domain find each other) ✓
- No firewall issues ✓

## Files

The `publisher.py` and `subscriber.py` are in the current directory. They use RTI Connext DDS Python API with DynamicData.

## Rules

- **Find and fix the QoS incompatibility** - something in the QoS settings is preventing communication
- **Both files may need changes** - check the QoS on both sides
- **Don't change the type or topic** - they're already correct

## QoS Reference

DDS Quality of Service controls how data is delivered. Some QoS policies follow "Request-Offered" (RxO) semantics where:
- The **writer** makes an "offer" about what it can provide
- The **reader** makes a "request" about what it needs
- If the offer doesn't satisfy the request, **they won't match**

Key RxO policies include: durability, deadline, latency budget, liveliness, reliability, destination order, and ownership.

## Testing

Fix the code so communication works. Run both programs and verify the subscriber receives all samples:

```bash
# Terminal 1
python publisher.py --count 10

# Terminal 2
python subscriber.py --count 10 --timeout 30
```

The subscriber should output JSON for each received reading.

## Expected outcome

After fixing the QoS mismatch, the subscriber should receive all samples from the publisher regardless of which one starts first.
