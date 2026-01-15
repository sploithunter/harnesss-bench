# Task: Fix Late Joiner Durability Bug

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- Two files exist: `publisher.py` and `subscriber.py` (check the workspace)
- Run `python test_durability.py` to verify your solution

## The Problem

The existing publisher and subscriber work fine when the subscriber starts first, but when the publisher starts first and sends messages, the subscriber misses them!

```
Works:                    Broken:
  Sub starts               Pub starts, sends 10
  Pub starts, sends 10     Sub starts
  Sub gets 10 ✓            Sub gets 0 ✗
```

In production, we can't control which one starts first. Both startup orders must work.

## Your Task

1. Look at the existing `publisher.py` and `subscriber.py` files
2. Identify the QoS configuration issues causing this bug
3. Fix BOTH files so that the subscriber receives all samples regardless of startup order

## Rules

- **Use DDS features** to solve this - that's what they're for
- **No timing hacks** - can't just add sleep() to wait for each other
- **No external synchronization** - pretend you can't add coordination code
- Both files may need changes

## Hints

- DDS has different QoS (Quality of Service) settings
- Something called "durability" controls whether late joiners get historical data
- There are also reliability and history settings that affect data delivery
- The publisher may need to wait longer at the end for late joiners

## Test Your Solution

Run: `python test_durability.py`

This test runs 5 trials with random startup order. All must pass.
