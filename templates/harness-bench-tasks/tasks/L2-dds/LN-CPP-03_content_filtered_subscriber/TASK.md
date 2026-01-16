# Task: Create C++ DDS Subscriber with Content Filtering

## Objective

Create a DDS subscriber in C++ using the Modern C++ API that uses a **ContentFilteredTopic** to receive only messages matching specific filter criteria.

## Scenario

A sensor network publishes readings from multiple sensors. Your subscriber must filter to receive only readings from a specific sensor within a value range. The filter criteria are provided via command line arguments.

## Type Specification

| Field | IDL Type | Description |
|-------|----------|-------------|
| sensor_id | string<64> | Sensor identifier (e.g., "sensor_A", "sensor_B") |
| value | double | Sensor reading value |
| timestamp | long long | Unix timestamp in milliseconds |

## Behavior

1. Parse command line arguments:
   - `--sensor ID` - Filter for this sensor_id (required)
   - `--min-value V` - Minimum value threshold (default: 0.0)
   - `--max-value V` - Maximum value threshold (default: 100.0)
   - `--count N` - Number of samples to receive (default: 5)
   - `--timeout T` - Timeout in seconds (default: 30)
   - `--domain D` - DDS domain ID (default: 0)

2. Create a ContentFilteredTopic that filters for:
   - `sensor_id` equals the sensor argument
   - `value` is between min-value and max-value (inclusive)

3. Subscribe using the ContentFilteredTopic (not the base topic)

4. Use RELIABLE reliability, TRANSIENT_LOCAL durability, KEEP_ALL history

5. For each received sample, output JSON to stdout:
   ```
   {"sensor_id":"...", "value":N.N, "timestamp":N}
   ```

6. Exit 0 if count samples received, exit 1 otherwise

## Key Requirements

- **Must use ContentFilteredTopic** - the DDS middleware must apply the filter, not your application code
- Filter parameters must come from command line arguments (not hardcoded)
- Topic name: "SensorData"
- Type name: "SensorReading"

## Provided Files

- `SensorReading.idl` - Type definition

## Required Files

1. `subscriber.cxx` - The C++ subscriber using Modern C++ API (dds:: namespace)
2. `CMakeLists.txt` - Build configuration

## Environment

- `$NDDSHOME` points to RTI Connext DDS installation
- `$CONNEXTDDS_ARCH` contains the target architecture
- `rtiddsgen -language C++11` will be run automatically before cmake
- RTI Connext DDS Modern C++ API is available

## Build

```bash
mkdir build && cd build
cmake ..
make
```

## Verification

A Python publisher will send 20 samples from 4 different sensors with varying values. Your subscriber will be called with `--sensor sensor_B --min-value 25 --max-value 75 --count 3`. Only samples matching ALL filter criteria should be received.
