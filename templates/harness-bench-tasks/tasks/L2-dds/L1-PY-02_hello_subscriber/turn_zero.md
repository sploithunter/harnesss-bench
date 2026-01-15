# Task: Create DDS Hello World Subscriber

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- A reference publisher sends "HelloWorld" messages on domain 0
- Run `python test_subscriber.py` to verify your solution

## The Scenario

You need to create a subscriber that receives "HelloWorld" messages and prints them. The messages have two fields: `message` (string) and `count` (integer).

## Your Task

Create `subscriber.py` that:

1. Subscribes to the "HelloWorld" topic on **domain 0**
2. Receives samples and prints each one as JSON (one per line, JSONL format)
3. Accepts command line arguments:
   - `--count N` or `-c N`: receive N samples (default 10)
   - `--timeout T` or `-t T`: max wait time in seconds (default 30)
4. Uses **async DDS patterns** - NOT busy-waiting/polling
5. Handles SIGTERM/SIGINT for graceful shutdown

## Output Format

Each sample printed as a single JSON line to stdout:
```
{"message": "Hello World 1", "count": 1}
{"message": "Hello World 2", "count": 2}
```

## Hints

- DDS has WaitSet and ReadCondition for async data reception
- Look into DynamicData for runtime type creation
- Use appropriate QoS (RELIABLE, TRANSIENT_LOCAL) to ensure delivery

## Test Your Solution

Run: `python test_subscriber.py`
