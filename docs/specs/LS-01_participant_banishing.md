# LS-01: DDS Participant Banishing

## Task Metadata

| Field | Value |
|-------|-------|
| **ID** | LS-01_participant_banishing |
| **Name** | DDS Security - Dynamic Participant Banishing |
| **Category** | L2-dds |
| **Difficulty** | Expert |
| **Language** | C |
| **Time Limit** | 900s |
| **Source Example** | `$NDDSHOME/resource/template/rti_workspace/examples/connext_dds/c/hello_banish/` |

## Description

Implement a DDS security monitoring application that can dynamically banish (revoke access for) participants based on their certificate subject name. This tests understanding of DDS Security Plugins, discovery APIs, and dynamic access control.

## Background

DDS Security Plugins provide authentication, access control, and cryptography for DDS communications. Key concepts:

- **Subject Name**: X.509 certificate identity (e.g., `CN=RTI ECDSA01 PEER03, O=Real Time Innovations`)
- **Participant Discovery**: DDS automatically discovers remote participants
- **Banishing**: Revoking a participant's access by redistributing encryption keys, excluding the banished participant

Relevant APIs:
- `DDS_DomainParticipant_get_discovered_participant_subject_name()`
- `DDS_DomainParticipant_get_discovered_participants_from_subject_name()`
- `DDS_DomainParticipant_banish_ignored_participants()`
- `DDS_DomainParticipant_ignore_participant()`

## Requirements

### Task A: Subject Name Discovery (Moderate)
Create a C program that:
1. Joins a secure DDS domain (domain 0) with provided security configuration
2. Discovers remote participants
3. Prints the X.509 subject name of each discovered participant
4. Outputs in format: `DISCOVERED: <subject_name>`

### Task B: Dynamic Banishing (Expert)
Extend the program to:
1. Accept a subject name pattern via command line argument
2. Ignore all participants matching that pattern
3. Call `banish_ignored_participants()` to redistribute keys
4. Confirm banishment by printing `BANISHED: <subject_name>`
5. Continue receiving data only from non-banished participants

## Provided Files

```
LS-01_participant_banishing/
├── TASK.md                    # Task prompt
├── HelloWorld.idl             # IDL type definition
├── USER_QOS_PROFILES.xml      # Security-enabled QoS profile
├── certs/                     # Pre-generated test certificates
│   ├── ca/
│   │   └── ca_cert.pem
│   ├── peer01/
│   │   ├── peer01_cert.pem
│   │   └── peer01_key.pem
│   └── peer02/
│       ├── peer02_cert.pem
│       └── peer02_key.pem
├── governance.xml             # Security governance document
├── permissions_peer01.xml     # Permissions for peer01
└── permissions_peer02.xml     # Permissions for peer02
```

## Expected Output

```
security_monitor.c
```

The program should compile with:
```bash
$NDDSHOME/bin/rtiddsgen -language C -example x64Darwin17clang9.0 HelloWorld.idl
make -f makefile_HelloWorld_x64Darwin17clang9.0
```

## Verification

### verify.sh
```bash
#!/bin/bash

# Start reference publisher (peer01) in background
./ref_publisher --domain 0 --cert peer01 &
PUB_PID=$!
sleep 2

# Start reference subscriber (peer02) in background
./ref_subscriber --domain 0 --cert peer02 &
SUB_PID=$!
sleep 2

# Run agent's security monitor
timeout 30s ./security_monitor --domain 0 --cert monitor --banish "PEER02" 2>&1 | tee output.log

# Check for required outputs
grep -q "DISCOVERED:.*PEER01" output.log && echo "PASS: Discovered PEER01"
grep -q "DISCOVERED:.*PEER02" output.log && echo "PASS: Discovered PEER02"
grep -q "BANISHED:.*PEER02" output.log && echo "PASS: Banished PEER02"

# Verify PEER02 stopped receiving after banishment
# (Reference subscriber logs should show crypto errors)

kill $PUB_PID $SUB_PID 2>/dev/null
```

### Success Criteria
1. Program compiles without errors
2. Discovers and prints subject names of remote participants
3. Successfully banishes specified participant
4. Non-banished participants continue communicating

## Internal Notes (DO NOT include in TASK.md)

These are implementation notes for spec authors. The actual TASK.md should NOT include API hints:

**Key APIs the agent must discover:**
- `DDS_DomainParticipant_get_discovered_participants()`
- `DDS_DomainParticipant_get_discovered_participant_subject_name()`
- `DDS_DomainParticipant_ignore_participant()`
- `DDS_DomainParticipant_banish_ignored_participants()`

**What TASK.md should say:**
- "Create a security monitoring application that can revoke participant access"
- "The application must discover remote participants and their identities"
- "Use the Security Plugins APIs to implement dynamic access control"
- Point only to `$NDDSHOME` as the library location

## Difficulty Justification

This task is rated **Expert** because:
1. Security Plugins APIs are sparsely documented
2. Requires understanding of X.509 certificates and PKI
3. Certificate file paths must be correctly configured in XML
4. The banish API has subtle semantics (ignore first, then banish)
5. Multi-participant coordination required for verification
6. Crypto library linking (OpenSSL/wolfSSL) adds complexity

## Dependencies

- RTI Connext DDS 7.x with Security Plugins
- OpenSSL 3.x or wolfSSL
- Pre-generated certificates (provided)
- C compiler with security library support

## Related Tasks

- LD-07: Discovery GUID Mining (prerequisite knowledge)
- LQ-01: QoS configuration (security QoS profiles)
