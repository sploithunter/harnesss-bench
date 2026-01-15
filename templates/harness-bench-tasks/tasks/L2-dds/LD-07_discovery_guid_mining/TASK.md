# Task: Discovery GUID Mining

## Critical Development Principle

**TEST EARLY, TEST OFTEN** - Test each approach incrementally.

## Background: DDS Discovery

Every DDS entity has a globally unique identifier (GUID):
- Participants have GUIDs
- DataWriters have GUIDs
- DataReaders have GUIDs

These GUIDs are exchanged during discovery via **built-in topics**:
- `DCPSParticipant` - Info about remote participants
- `DCPSPublication` - Info about remote DataWriters
- `DCPSSubscription` - Info about remote DataReaders

## Your Tasks

### Task A: Subscriber Gets Publisher's GUID (Easier)

When a subscriber receives a sample, it can determine which publisher sent it.

**Goal**: Create a subscriber that prints the GUID of the publisher for each received sample.

**Hint**: The sample info contains a `publication_handle` that identifies the source.

```python
for sample in reader.take():
    if sample.info.valid:
        # sample.info contains metadata about the sample
        pub_handle = sample.info.publication_handle
        # Convert handle to GUID...
```

**Key APIs to explore**:
- `sample.info.publication_handle`
- `reader.matched_publication_data(handle)`
- InstanceHandle and GUID relationship

---

### Task B: Publisher Gets Subscriber's GUIDs (Harder)

A publisher wants to know all subscribers to its topic BEFORE publishing.

**Goal**: Create a publisher that discovers and prints all subscriber GUIDs for its topic.

**The Challenge**: The publisher doesn't directly receive data from subscribers.
It must use the **built-in topics** to discover remote entities.

**Approach**:
1. Get the built-in subscriber from the participant
2. Get the DCPSSubscription DataReader
3. Read subscription data to find remote subscribers
4. Filter for subscribers to your topic
5. Extract their GUIDs

```python
# Get built-in subscriber
builtin_subscriber = participant.builtin_subscriber

# The DCPSSubscription topic contains info about all DataReaders
# in the domain that this participant has discovered
subscription_reader = builtin_subscriber.lookup_datareader("DCPSSubscription")

# Read to find remote subscribers
for sample in subscription_reader.read():
    if sample.info.valid:
        sub_data = sample.data
        # sub_data contains: topic_name, participant_key, key (GUID), QoS, etc.
        if sub_data.topic_name == "YourTopicName":
            print(f"Found subscriber: {sub_data.key}")
```

---

## RTI Connext Specific APIs

### Getting Matched Publications (for subscriber)

```python
# Get list of matched publication handles
matched_pubs = reader.matched_publications

for pub_handle in matched_pubs:
    # Get detailed info about this publication
    pub_data = reader.matched_publication_data(pub_handle)
    print(f"Publisher GUID: {pub_data.key}")
    print(f"Topic: {pub_data.topic_name}")
```

### Built-in Topics (for publisher → subscriber discovery)

```python
# Access built-in subscriber
builtin_sub = participant.builtin_subscriber

# Built-in readers for each discovery topic
participant_reader = builtin_sub.lookup_datareader("DCPSParticipant")
publication_reader = builtin_sub.lookup_datareader("DCPSPublication")
subscription_reader = builtin_sub.lookup_datareader("DCPSSubscription")

# Read subscription info
for sample in subscription_reader.take():
    if sample.info.valid:
        # SubscriptionBuiltinTopicData contains:
        # - key: GUID of the DataReader
        # - participant_key: GUID of its participant
        # - topic_name: Topic it subscribes to
        # - type_name: Type name
        # - durability, reliability, etc.: QoS
        print(f"Remote subscriber: {sample.data.key}")
```

---

## Expected Output

### Task A Output (Subscriber)
```
Received sample from publisher GUID: 01.02.03.04.05.06.07.08.09.0a.0b.0c|0.0.1.c1
Received sample from publisher GUID: 01.02.03.04.05.06.07.08.09.0a.0b.0c|0.0.1.c1
...
```

### Task B Output (Publisher)
```
Discovered subscriber GUID: 0a.0b.0c.0d.0e.0f.10.11.12.13.14.15|0.0.1.c7
Discovered subscriber GUID: 1a.1b.1c.1d.1e.1f.20.21.22.23.24.25|0.0.1.c7
Ready to publish to 2 subscribers...
```

---

## Why This Matters

Real-world uses:
- **Debugging**: "Who is my publisher?" / "Who is receiving my data?"
- **Security**: Verify expected participants
- **Monitoring**: Track system topology
- **Failover**: Detect when publishers/subscribers join/leave

---

## Files to Create

Create these files in the **workspace root directory** (NOT in a subdirectory):

1. `subscriber_gets_pub_guid.py` - Task A implementation
   - Should accept `--count N` and `--timeout T` command line args
   - Output JSONL with `publisher_guid` field for each sample

2. `publisher_gets_sub_guids.py` - Task B implementation
   - Discovers subscribers before publishing
   - Prints discovered subscriber GUIDs

---

## Success Criteria

### Task A
- [ ] Subscriber receives samples
- [ ] Correctly extracts publisher handle from sample info
- [ ] Converts handle to GUID
- [ ] Prints publisher GUID for each sample

### Task B
- [ ] Publisher accesses built-in subscriber
- [ ] Reads from DCPSSubscription topic
- [ ] Filters for subscribers to its topic
- [ ] Extracts and prints subscriber GUIDs
- [ ] Does this BEFORE publishing (proves discovery works)

---

## CRITICAL: DDS Interoperability Requirements

**Topic names must match EXACTLY.** If your publisher publishes on `"HelloWorld"`, subscribers must subscribe to exactly `"HelloWorld"`. The built-in topics will report the exact topic names - use these for filtering.

**For this task**: When filtering DCPSSubscription by topic name, use the EXACT topic name string - character-for-character match required.

## Common Mistakes

1. **Confusing InstanceHandle and GUID**: They're related but different
2. **Not waiting for discovery**: Built-in topic data takes time to populate
3. **Wrong built-in topic**: DCPSSubscription for subscribers, DCPSPublication for publishers
4. **Filtering by topic**: Remember to check `topic_name` matches EXACTLY (case-sensitive)


