#!/usr/bin/env python3
"""Reference subscriber using ContentFilteredTopic.

Receives only samples matching: id > 50 AND value > 75.0
"""

import argparse
import json
import signal
import sys
import time

import rti.connextdds as dds


running = True


def signal_handler(signum, frame):
    global running
    running = False


def create_sensor_type():
    sensor_type = dds.StructType("SensorReading")
    sensor_type.add_member(dds.Member("id", dds.Int32Type()))
    sensor_type.add_member(dds.Member("value", dds.Float64Type()))
    sensor_type.add_member(dds.Member("timestamp", dds.Float64Type()))
    return sensor_type


def main():
    global running
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=100,
                        help="Expected matching samples")
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    participant = dds.DomainParticipant(args.domain)
    
    sensor_type = create_sensor_type()
    
    # Create base topic
    topic = dds.DynamicData.Topic(participant, "SensorReadings", sensor_type)
    
    # Create ContentFilteredTopic with SQL filter expression
    # This filters at the DDS level - non-matching samples are not sent
    # API: ContentFilteredTopic(topic, name, contentfilter)
    cft = dds.DynamicData.ContentFilteredTopic(
        topic,               # Base topic first
        "FilteredSensors",   # Name for filtered topic
        dds.Filter("id > 50 AND value > 75.0")  # SQL filter
    )
    
    subscriber = dds.Subscriber(participant)
    
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    # Create reader on FILTERED topic, not base topic
    reader = dds.DynamicData.DataReader(subscriber, cft, reader_qos)
    
    # WaitSet pattern
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)
    
    received_count = 0
    start_time = time.time()
    
    while running and received_count < args.count:
        elapsed = time.time() - start_time
        remaining = args.timeout - elapsed
        
        if remaining <= 0:
            break
        
        wait_time = min(1.0, remaining)
        active = waitset.wait(dds.Duration.from_seconds(wait_time))
        
        if read_condition in active:
            for sample in reader.take():
                if sample.info.valid:
                    # All samples here already match the filter!
                    output = {
                        "id": sample.data["id"],
                        "value": sample.data["value"],
                        "timestamp": sample.data["timestamp"],
                    }
                    print(json.dumps(output), flush=True)
                    received_count += 1
                    
                    if received_count >= args.count:
                        break
    
    print(f"Received {received_count} matching samples", file=sys.stderr)


if __name__ == "__main__":
    main()

