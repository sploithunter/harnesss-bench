#!/usr/bin/env python3
"""Publisher for Content Filtered Topic test.

Publishes sensor readings to topic "SensorReadings" on domain 0.

Data structure:
    - id: integer (sensor ID, 1-100)
    - value: float64 (sensor value, 0-100)
    - timestamp: float64 (unix timestamp)

The subscriber should use ContentFilteredTopic to filter:
    id > 50 AND value > 75.0

Usage:
    python publisher.py [--samples N] [--domain D]
"""

import argparse
import time
import sys

import rti.connextdds as dds


def create_sensor_type():
    """Create the SensorReading type using DynamicData."""
    sensor_type = dds.StructType("SensorReading")
    sensor_type.add_member(dds.Member("id", dds.Int32Type()))
    sensor_type.add_member(dds.Member("value", dds.Float64Type()))
    sensor_type.add_member(dds.Member("timestamp", dds.Float64Type()))
    return sensor_type


def main():
    parser = argparse.ArgumentParser(description="Sensor data publisher")
    parser.add_argument("--samples", "-s", type=int, default=200, 
                        help="Total samples to publish (default: 200)")
    parser.add_argument("--domain", "-d", type=int, default=0,
                        help="DDS domain ID (default: 0)")
    args = parser.parse_args()
    
    # Create DDS entities
    participant = dds.DomainParticipant(args.domain)
    sensor_type = create_sensor_type()
    topic = dds.DynamicData.Topic(participant, "SensorReadings", sensor_type)
    
    publisher = dds.Publisher(participant)
    
    # QoS for reliable delivery to late joiners
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    writer_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    writer_qos.history.kind = dds.HistoryKind.KEEP_ALL
    
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    
    # Wait for subscriber discovery
    print("Waiting for subscribers...", file=sys.stderr)
    time.sleep(2.0)
    
    # Publish test data with boundary values for filter testing
    # Filter: id > 50 AND value > 75.0
    test_ids = [49, 50, 51, 74, 75, 76]      # 51, 74, 75, 76 pass id > 50
    test_values = [74.0, 75.0, 76.0]          # Only 76.0 passes value > 75.0
    
    matching_count = 0
    
    for i in range(args.samples):
        sensor_id = test_ids[i % len(test_ids)]
        value = test_values[i % len(test_values)]
        
        sample = dds.DynamicData(sensor_type)
        sample["id"] = sensor_id
        sample["value"] = value
        sample["timestamp"] = time.time()
        
        # Track how many match the filter: id > 50 AND value > 75.0
        if sensor_id > 50 and value > 75.0:
            matching_count += 1
        
        writer.write(sample)
        
        if (i + 1) % 50 == 0:
            print(f"Published {i + 1}/{args.samples}", file=sys.stderr)
        
        time.sleep(0.01)  # 10ms between samples
    
    # Allow time for delivery
    time.sleep(2.0)
    
    print(f"Done. Published {args.samples} samples.", file=sys.stderr)
    print(f"Samples matching filter (id>50 AND value>75): {matching_count}", file=sys.stderr)


if __name__ == "__main__":
    main()

