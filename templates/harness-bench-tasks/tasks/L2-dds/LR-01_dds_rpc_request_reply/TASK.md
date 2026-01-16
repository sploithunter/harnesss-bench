# Task: Create DDS RPC Client for Calculator Service

## Objective

Create a DDS RPC client that can call functions on a Calculator service. The service is already running and waiting for requests.

## The Service

A Calculator service is running on **domain 0** with **service_name "CalculatorService"**.

It accepts requests and returns replies using these types:

**Request Type** (`CalculatorRequest`):
| Field | Type | Description |
|-------|------|-------------|
| operation | string(64) | Operation: "add", "subtract", "multiply" |
| a | int32 | First operand |
| b | int32 | Second operand |

**Reply Type** (`CalculatorReply`):
| Field | Type | Description |
|-------|------|-------------|
| result | int32 | Calculation result |
| success | bool | Whether operation succeeded |
| error | string(256) | Error message if failed |

## Your Task

Create `client.py` that:
1. Connects to the CalculatorService
2. Parses command line: `--op OPERATION --a NUM --b NUM`
3. Sends a calculation request
4. Receives and prints the result as JSON: `{"result": N, "success": true/false}`

## Example Usage

```bash
python client.py --op add --a 10 --b 5
# Expected output: {"result": 15, "success": true}

python client.py --op multiply --a 4 --b 7
# Expected output: {"result": 28, "success": true}
```

## Environment

- RTI Connext DDS Python API is available (`rti.connextdds`)
- The RPC module is at `rti.rpc`
- Types can be defined with `rti.types` (imported as `idl`)

## Requirements

1. Type names must match exactly: `CalculatorRequest`, `CalculatorReply`
2. Field names must match exactly as shown above
3. String fields need length bounds (use IDL annotations)
4. Wait for service discovery before sending (timeout after 5 seconds if not found)
5. Handle the case where no reply is received

## Output Format

Print exactly one JSON line to stdout:
- On success: `{"result": N, "success": true}`
- On failure: `{"result": 0, "success": false, "error": "message"}`
