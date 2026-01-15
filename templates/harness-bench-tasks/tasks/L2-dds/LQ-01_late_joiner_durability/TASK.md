# Bug: Subscriber misses messages when it starts late

I have a publisher and subscriber that work fine when the subscriber starts first, but when the publisher starts first and sends messages, the subscriber misses them!

## The problem

```
Works:                    Broken:
  Sub starts               Pub starts, sends 10
  Pub starts, sends 10     Sub starts
  Sub gets 10 ✓            Sub gets 0 ✗
```

In production, we can't control which one starts first. Both orders need to work.

## Files

The `publisher.py` and `subscriber.py` are in the current directory. They use RTI Connext DDS Python API.

## Rules

- **Use DDS features** to solve this - that's what they're for
- **No timing hacks** - can't use sleep() to wait for each other
- **No synchronization** - pretend we can't add coordination code
- Both files may need changes

## What I know

- DDS has different QoS (Quality of Service) settings
- Something about "durability" controls whether late joiners get old data?
- There's a `dds-spy-wrapper` tool to verify data flow

## CRITICAL: DDS Interoperability Requirements

**Do not change topic or type names.** The existing code has matching topic and type names - keep them exactly as-is. If you rename them, publisher and subscriber won't communicate.

**Keep type approach consistent.** If the existing code uses DynamicData, keep using DynamicData. If it uses `@idl.struct`, keep using that. Mixing approaches breaks communication.

**QoS must be compatible.** The fix involves QoS settings, but make sure both publisher and subscriber have compatible settings. Some QoS combinations prevent communication.

## Testing

Run `python test_durability.py` - it tests random startup order 5 times. All must pass.

## Help!

Can you look at the files and fix the QoS settings? Please explain what you changed and why.
