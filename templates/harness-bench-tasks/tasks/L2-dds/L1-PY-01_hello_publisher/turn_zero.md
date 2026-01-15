# Task: Create DDS Hello World Publisher

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- Run `python test_publisher.py` to verify your solution

## The Scenario

You're new to RTI Connext DDS and need to create a simple publisher in Python. You've heard about something called "DynamicData" that lets you create types at runtime without needing IDL files.

## Your Task

Create `publisher.py` that:

1. Creates a topic called "HelloWorld" with two fields:
   - `message`: a string (max 256 characters)
   - `count`: an integer

2. Publishes exactly **10 samples** at **2 Hz** (every 0.5 seconds)

3. Each sample should have:
   - `message` = "Hello World 1", "Hello World 2", ..., "Hello World 10"
   - `count` = 1, 2, 3, ..., 10

4. Uses **domain 85**

5. Waits appropriately for DDS discovery before publishing

## Hints

- Look into RTI's DynamicData API for runtime type creation
- DDS entities need time to discover each other
- The Publisher needs a DomainParticipant, Topic, and DataWriter

## Test Your Solution

Run: `python test_publisher.py`
