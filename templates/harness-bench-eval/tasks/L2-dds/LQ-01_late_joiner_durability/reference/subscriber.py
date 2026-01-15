#!/usr/bin/env python3
"""Sensor Data Subscriber - FIXED: Uses TRANSIENT_LOCAL durability.

This is the correct implementation that receives all samples
regardless of startup order.

KEY REQUIREMENTS for late joiner durability:
1. TRANSIENT_LOCAL - tells DDS to request cached data from writer
2. RELIABLE - enables the resend mechanism (required for late joiner delivery)
3. KEEP_ALL - ensures all samples are stored/received (not just the last one)
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

    # CRITICAL: All three QoS settings are required for late joiner durability
    # - TRANSIENT_LOCAL: Request historical data from writer's cache
    # - RELIABLE: Enables resend mechanism (without this, late joiners get nothing!)
    # - KEEP_ALL: Store all samples, not just the most recent one
    reader_qos = dds.DataReaderQos()
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL

    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)

    # WaitSet pattern for reading
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
        try:
            waitset.wait(dds.Duration.from_seconds(wait_time))
        except dds.TimeoutError:
            pass

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
