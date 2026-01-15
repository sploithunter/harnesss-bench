#!/usr/bin/env python3
"""Task B: Publisher discovers Subscriber GUIDs via built-in topics.

This demonstrates the harder task: a publisher discovering all subscribers
to its topic BEFORE publishing, using DDS built-in topics.
"""

import argparse
import sys
import time

import rti.connextdds as dds


def create_hello_type():
    hello_type = dds.StructType("HelloWorld")
    hello_type.add_member(dds.Member("message", dds.StringType(256)))
    hello_type.add_member(dds.Member("count", dds.Int32Type()))
    return hello_type


def discover_subscribers(participant, topic_name, timeout=10.0):
    """Discover all subscribers to a given topic using built-in topics.
    
    This uses the DCPSSubscription built-in topic which contains
    information about all DataReaders discovered in the domain.
    """
    discovered_subs = {}
    
    # Get the built-in subscriber
    builtin_subscriber = participant.builtin_subscriber
    
    # Get the DCPSSubscription reader
    # This reader receives data about remote DataReaders
    subscription_reader = builtin_subscriber.lookup_datareader("DCPSSubscription")
    
    if subscription_reader is None:
        print("ERROR: Could not get DCPSSubscription reader", file=sys.stderr)
        return discovered_subs
    
    # Use WaitSet to wait for subscription data
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(
        subscription_reader, 
        dds.DataState.any_data
    )
    waitset.attach_condition(read_condition)
    
    start_time = time.time()
    
    print(f"Discovering subscribers to topic '{topic_name}'...", file=sys.stderr)
    
    while time.time() - start_time < timeout:
        # Wait for subscription discovery data
        active = waitset.wait(dds.Duration.from_seconds(1.0))
        
        if read_condition in active:
            # Read all available subscription data
            samples = subscription_reader.take()
            
            for sample in samples:
                if sample.info.valid:
                    sub_data = sample.data
                    
                    # Check if this subscriber is for our topic
                    if sub_data.topic_name == topic_name:
                        sub_guid = str(sub_data.key)
                        
                        if sub_guid not in discovered_subs:
                            discovered_subs[sub_guid] = {
                                "guid": sub_guid,
                                "topic_name": sub_data.topic_name,
                                "type_name": sub_data.type_name,
                                "participant_key": str(sub_data.participant_key),
                            }
                            print(f"  Found subscriber: {sub_guid}", file=sys.stderr)
        
        # Also check matched subscriptions on the writer (alternative method)
        # This is done below after the writer is created
    
    return discovered_subs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--domain", "-d", type=int, default=0)
    parser.add_argument("--discovery-wait", type=float, default=5.0,
                        help="Time to wait for subscriber discovery")
    args = parser.parse_args()
    
    participant = dds.DomainParticipant(args.domain)
    
    hello_type = create_hello_type()
    topic = dds.DynamicData.Topic(participant, "HelloWorld", hello_type)
    
    # First, discover subscribers BEFORE creating writer
    # (Using built-in topics)
    print("=== Phase 1: Discover via built-in topics ===", file=sys.stderr)
    discovered_via_builtin = discover_subscribers(
        participant, "HelloWorld", timeout=args.discovery_wait
    )
    
    # Now create the publisher/writer
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    
    # Wait for discovery to complete
    time.sleep(2.0)
    
    # Alternative method: Use matched_subscriptions on the writer
    print("\n=== Phase 2: Discover via matched_subscriptions ===", file=sys.stderr)
    matched_subs = writer.matched_subscriptions
    
    for sub_handle in matched_subs:
        try:
            sub_data = writer.matched_subscription_data(sub_handle)
            sub_guid = str(sub_data.key)
            print(f"  Matched subscriber: {sub_guid}", file=sys.stderr)
        except Exception as e:
            print(f"  Could not get sub data: {e}", file=sys.stderr)
    
    # Summary
    print(f"\n=== Summary ===", file=sys.stderr)
    print(f"Discovered via built-in topics: {len(discovered_via_builtin)}", file=sys.stderr)
    print(f"Matched subscriptions: {len(matched_subs)}", file=sys.stderr)
    
    # Print all discovered subscribers
    print("\nAll discovered subscribers:", file=sys.stderr)
    for guid, info in discovered_via_builtin.items():
        print(f"  {guid}", file=sys.stderr)
    
    # Now publish (if we found subscribers, or publish anyway)
    total_subs = len(discovered_via_builtin) + len(matched_subs)
    if total_subs == 0:
        print("\nWARNING: No subscribers discovered. Publishing anyway...", 
              file=sys.stderr)
    else:
        print(f"\nPublishing to {total_subs} discovered subscriber(s)...", 
              file=sys.stderr)
    
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(hello_type)
        sample["message"] = f"Hello World {i}"
        sample["count"] = i
        writer.write(sample)
        print(f"Published: count={i}", file=sys.stderr)
        time.sleep(0.5)
    
    time.sleep(2.0)
    print(f"\nPublished {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()


