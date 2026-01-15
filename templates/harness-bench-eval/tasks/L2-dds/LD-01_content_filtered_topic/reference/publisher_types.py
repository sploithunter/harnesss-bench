#!/usr/bin/env python3
"""Reference publisher using rti.types.struct for Content Filtered Topic test.

Publishes sensor readings with deterministic boundary values for testing.
Filter: id > 50 AND value > 75.0

Uses rti.types.struct decorator (a third type system in RTI Connext Python).
"""

import argparse
import time
import sys

import rti.connextdds as dds
from rti.types import struct, int32, float64


@struct
class SensorReading:
    id: int32 = 0
    value: float64 = 0.0
    timestamp: float64 = 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", "-s", type=int, default=500, 
                        help="Total samples to publish")
    parser.add_argument("--domain", "-d", type=int, default=0)
    args = parser.parse_args()
    
    participant = dds.DomainParticipant(args.domain)
    
    topic = dds.Topic(participant, "SensorReadings", SensorReading)
    
    publisher = dds.Publisher(participant)
    
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DataWriter(publisher, topic, writer_qos)
    
    # Wait for subscriber discovery
    time.sleep(2.0)
    
    # Deterministic boundary test values
    # Filter: id > 50 AND value > 75.0
    test_ids = [49, 50, 51, 74, 75, 76]      # 51, 74, 75, 76 pass id > 50
    test_values = [74.0, 75.0, 76.0]          # Only 76.0 passes value > 75.0
    
    matching_count = 0
    
    for i in range(args.samples):
        sensor_id = test_ids[i % len(test_ids)]
        value = test_values[i % len(test_values)]
        
        sample = SensorReading(
            id=sensor_id,
            value=value,
            timestamp=time.time()
        )
        
        # Track how many match the filter: id > 50 AND value > 75.0
        if sensor_id > 50 and value > 75.0:
            matching_count += 1
        
        writer.write(sample)
        
        if (i + 1) % 100 == 0:
            print(f"Published {i + 1}/{args.samples}", file=sys.stderr)
        
        time.sleep(0.01)  # 10ms between samples
    
    # Allow time for delivery
    time.sleep(2.0)
    
    print(f"Published {args.samples} total samples", file=sys.stderr)
    print(f"Matching filter (id>50 AND value>75): {matching_count}", file=sys.stderr)


if __name__ == "__main__":
    main()


