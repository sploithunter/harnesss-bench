#!/usr/bin/env python3
"""Temperature Monitor Publisher - sends periodic readings.

This publisher sends temperature data to any interested subscribers.
"""

import argparse
import time
import sys

import rti.connextdds as dds


def create_temperature_type():
    temp_type = dds.StructType("TemperatureReading")
    temp_type.add_member(dds.Member("device_id", dds.StringType(64)))
    temp_type.add_member(dds.Member("celsius", dds.Float64Type()))
    temp_type.add_member(dds.Member("reading_num", dds.Int32Type()))
    return temp_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()

    participant = dds.DomainParticipant(args.domain)

    temp_type = create_temperature_type()
    topic = dds.DynamicData.Topic(participant, "TemperatureReading", temp_type)

    publisher = dds.Publisher(participant)

    # QoS setup - we want fast delivery, don't need guaranteed delivery
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_LAST
    writer_qos.history.depth = 10

    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

    # Give time for discovery
    time.sleep(0.5)

    # Publish samples
    for i in range(1, args.count + 1):
        sample = dds.DynamicData(temp_type)
        sample["device_id"] = "THERMO_LAB_01"
        sample["celsius"] = 22.5 + (i * 0.1)
        sample["reading_num"] = i

        writer.write(sample)
        print(f"Published: reading_num={i}, celsius={sample['celsius']:.1f}", file=sys.stderr)

        time.sleep(0.1)

    # Keep writer alive briefly for late joiners
    time.sleep(1.5)
    print(f"Published {args.count} samples", file=sys.stderr)


if __name__ == "__main__":
    main()
