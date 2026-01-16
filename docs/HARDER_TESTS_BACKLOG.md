# Harder DDS Test Ideas Backlog

Ideas for more challenging DDS benchmark tasks. Need to experiment with difficulty before building real tests.

## QoS-Based Tests

### QoS Mismatch Detection (Moderate)
- Create pub/sub pair with incompatible QoS
- Task: Diagnose why they don't communicate
- Example: RELIABLE pub + BEST_EFFORT sub (works), BEST_EFFORT pub + RELIABLE sub (fails)

### QoS Configuration (Moderate)
- Configure specific QoS: TRANSIENT_LOCAL durability, custom deadlines, lifespan
- Rate limiting with `DataWriterProtocol` flow controllers
- Liveliness assertions (manual vs automatic)

### QoS Compatibility Matrix (Hard)
- Given a subscriber QoS, find compatible publisher settings
- Multiple valid answers, test for any working combination

## Advanced Patterns

### Request-Reply Pattern (Hard)
- Implement RPC-style using `rti.connextdds.request` module
- Requester sends query, replier responds
- Less documented API

### Content Filter Expressions (Hard)
- Complex SQL-like filters: `"temp > 30 AND location LIKE 'sensor_%'"`
- Parameter binding for runtime filter changes
- Filter expression optimization

### Multi-Topic Correlation (Very Hard)
- Join data from multiple topics
- Time-based correlation of related samples

## Multi-Language Interop

### C++ Publisher / Python Subscriber (Very Hard)
- IDL-defined types generated for both languages
- Requires `rtiddsgen` for both, CMake + Python setup
- Type compatibility verification

### Java Integration (Very Hard)
- Maven/Gradle build system
- Different RTI Java API idioms

## Security

### DDS Security Configuration (Expert)
- Authentication with certificates
- Access control with permissions files
- Governance document creation

## Discovery & Networking

### Built-in Topic Mining (Already LD-07 - Only Opus/Sonnet pass)
- Uses `DCPSParticipant`, `DCPSSubscription` built-in topics
- This is currently our hardest test

### Multi-Domain Bridge (Hard)
- Route data between DDS domains
- Domain participant per domain, manual bridging

### Discovery Timing (Moderate-Hard)
- Wait for specific discovery events
- Handle late joiners, participant departure

## Complex Types

### Nested Structs & Sequences (Moderate)
- IDL with nested types, sequences, arrays
- DynamicData access patterns for nested fields

### Type Extensibility (Hard)
- Mutable vs final types
- Adding fields to existing types
- Backwards compatibility

### Union Types (Moderate)
- IDL unions with discriminators
- Switch-based data access

## Error Handling

### Graceful Degradation (Hard)
- Handle network partitions
- Reconnection logic
- Stale data detection

### Resource Exhaustion (Moderate)
- Handle queue overflow
- Sample rejection callbacks

---

## Priority Queue

1. **QoS Mismatch** - Good failure debugging test
2. **Content Filter Expressions** - Tests API knowledge depth
3. **C++ Interop** - We have infrastructure, extends existing
4. **Request-Reply** - Different paradigm, less documented
5. **Nested Types** - Tests DynamicData proficiency

## Notes

- LD-07 (GUID mining) remains the gold standard - only Claude Code with Opus/Sonnet 4.5 passes
- Tests should have clear pass/fail criteria
- Include API hints in TASK.md but not full solutions
- Can append new test results to existing benchmark without re-running old tests
