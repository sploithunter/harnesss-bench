#!/usr/bin/env python3
"""Sensor Data Subscriber - BROKEN: Misses historical data.

Problem: Uses VOLATILE durability, so it doesn't request historical data
from the writer's cache. If this subscriber starts late, it misses
all samples that were published before it joined.
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
    sensor_type = dds.StructType("SensorData")
    sensor_type.add_member(dds.Member("sensor_id", dds.StringType(64)))
    sensor_type.add_member(dds.Member("value", dds.Float64Type()))
    sensor_type.add_member(dds.Member("sequence", dds.Int32Type()))
    return sensor_type


def main():
    global running

    parser = argparse.ArgumentParser()
    parser.add_argument("--count", "-c", type=int, default=10)
    parser.add_argument("--timeout", "-t", type=float, default=30.0)
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    participant = dds.DomainParticipant(args.domain)

    sensor_type = create_sensor_type()
    topic = dds.DynamicData.Topic(participant, "SensorData", sensor_type)

    subscriber = dds.Subscriber(participant)

    # BUG: VOLATILE means we don't request historical data!
    reader_qos = dds.DataReaderQos()
    reader_qos.durability.kind = dds.DurabilityKind.VOLATILE
    reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT

    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)

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
                    output = {
                        "sensor_id": sample.data["sensor_id"],
                        "value": sample.data["value"],
                        "sequence": sample.data["sequence"],
                    }
                    print(json.dumps(output), flush=True)
                    received_count += 1

                    if received_count >= args.count:
                        break

    print(f"Received {received_count}/{args.count} samples", file=sys.stderr)
    return 0 if received_count >= args.count else 1


if __name__ == "__main__":
    sys.exit(main())
