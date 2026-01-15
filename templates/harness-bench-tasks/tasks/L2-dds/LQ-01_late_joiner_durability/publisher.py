#!/usr/bin/env python3
"""Sensor Data Publisher - BROKEN: Late joiners miss data.

Problem: Uses VOLATILE durability, so historical data is not stored.
When subscriber starts after publisher, it misses all previously sent data.
"""

import argparse
import time
import sys

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

    # BUG: VOLATILE means data is NOT stored for late joiners!
    writer_qos = dds.DataWriterQos()
    writer_qos.durability.kind = dds.DurabilityKind.VOLATILE
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT

    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

    # Publish samples
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(sensor_type)
        sample["sensor_id"] = "TEMP_001"
        sample["value"] = 20.0 + (i * 0.5)
        sample["sequence"] = i

        writer.write(sample)
        print(f"Published: sequence={i}, value={sample['value']}", file=sys.stderr)

        time.sleep(0.1)

    # Keep writer alive briefly
    time.sleep(1.0)
    print(f"Published {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()
