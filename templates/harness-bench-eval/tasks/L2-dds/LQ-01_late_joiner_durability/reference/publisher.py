#!/usr/bin/env python3
"""Sensor Data Publisher - FIXED: Uses TRANSIENT_LOCAL durability.

This is the correct implementation that works regardless of startup order.
TRANSIENT_LOCAL keeps data in writer's cache for late-joining subscribers.
"""

import argparse
import sys
import time

import rti.connextdds as dds


def create_sensor_type():
    sensor_type = dds.StructType("SensorData")
    sensor_type.add_member(dds.Member("sensor_id", dds.StringType(64)))
    sensor_type.add_member(dds.Member("value", dds.Float64Type()))
    sensor_type.add_member(dds.Member("sequence", dds.Int32Type()))
    return sensor_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()

    participant = dds.DomainParticipant(args.domain)

    sensor_type = create_sensor_type()
    topic = dds.DynamicData.Topic(participant, "SensorData", sensor_type)

    publisher = dds.Publisher(participant)

    # FIXED: TRANSIENT_LOCAL keeps data for late-joining subscribers
    # FIXED: RELIABLE ensures delivery confirmation
    # FIXED: KEEP_ALL ensures all samples are stored in writer cache
    writer_qos = dds.DataWriterQos()
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL

    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

    # Publish samples
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(sensor_type)
        sample["sensor_id"] = "TEMP_001"
        sample["value"] = 20.0 + (i * 0.5)
        sample["sequence"] = i

        writer.write(sample)
        print(f"Published: sequence={i}, value={sample['value']}", file=sys.stderr)

    # Keep writer alive to serve TRANSIENT_LOCAL cache to late joiners
    # This is necessary because the writer's cache is destroyed when it exits
    time.sleep(5.0)
    print(f"Published {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()
