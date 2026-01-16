#!/usr/bin/env python3
"""Temperature Monitor Subscriber - receives temperature readings.

This subscriber listens for temperature data from publishers.
It requires reliable delivery to ensure no readings are missed.
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


def create_temperature_type():
    temp_type = dds.StructType("TemperatureReading")
    temp_type.add_member(dds.Member("device_id", dds.StringType(64)))
    temp_type.add_member(dds.Member("celsius", dds.Float64Type()))
    temp_type.add_member(dds.Member("reading_num", dds.Int32Type()))
    return temp_type


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

    temp_type = create_temperature_type()
    topic = dds.DynamicData.Topic(participant, "TemperatureReading", temp_type)

    subscriber = dds.Subscriber(participant)

    # QoS setup - we need guaranteed delivery of all readings
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    reader_qos.history.kind = dds.HistoryKind.KEEP_ALL

    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)

    # WaitSet pattern
    waitset = dds.WaitSet()
    read_condition = dds.ReadCondition(reader, dds.DataState.any_data)
    waitset.attach_condition(read_condition)

    received_count = 0
    start_time = time.time()

    print(f"Waiting for temperature readings...", file=sys.stderr)

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
                        "device_id": sample.data["device_id"],
                        "celsius": sample.data["celsius"],
                        "reading_num": sample.data["reading_num"],
                    }
                    print(json.dumps(output), flush=True)
                    received_count += 1

                    if received_count >= args.count:
                        break

    print(f"Received {received_count}/{args.count} readings", file=sys.stderr)
    return 0 if received_count >= args.count else 1


if __name__ == "__main__":
    sys.exit(main())
