# Task: Discovery GUID Mining

## Environment
- RTI Connext DDS 7.x Python API is installed (`rti.connextdds`)
- Run `python test_discovery.py` to verify your solution

## Background

Every DDS entity has a globally unique identifier (GUID):
- Participants have GUIDs
- DataWriters have GUIDs
- DataReaders have GUIDs

These GUIDs are exchanged during DDS discovery. RTI Connext provides APIs to access this discovery information.

## Your Tasks

### Task A: subscriber_gets_pub_guid.py (Easier)

When a subscriber receives a sample, determine which publisher sent it.

**Goal**: Create `subscriber_gets_pub_guid.py` - a subscriber for "HelloWorld" topic that prints the GUID of the publisher for each received sample.

**Hint**: The sample info contains a `publication_handle` that identifies the source. You can use this to look up publisher details via `reader.matched_publication_data(handle)`.

**Output format** (JSONL to stdout):
```
{"sample": {"message": "Hello", "count": 1}, "publisher_guid": "01.02.03.04..."}
```

### Task B: publisher_gets_sub_guids.py (Harder)

A publisher wants to know all subscribers to its topic BEFORE publishing.

**Goal**: Create `publisher_gets_sub_guids.py` - a publisher that discovers and prints all subscriber GUIDs for the "HelloWorld" topic before it starts publishing.

**The Challenge**: The publisher doesn't receive data from subscribers. It must use DDS's **built-in topics** to discover remote entities. Look into:
- `DCPSParticipant` - info about remote participants
- `DCPSPublication` - info about remote DataWriters
- `DCPSSubscription` - info about remote DataReaders

**Output format** (JSONL to stdout):
```
{"type": "discovered_subscriber", "guid": "0a.0b.0c.0d..."}
```

## Hints

- Discovery takes time - wait a couple seconds after creating entities
- Look into `participant.builtin_subscriber` and `lookup_datareader()`
- Filter by `topic_name` to find subscribers to your specific topic

## Test Your Solution

Run: `python test_discovery.py`
