# DDS Benchmark Tasks Reference

Quick reference for all implemented DDS benchmark tasks.

## Task ID Naming Convention

Task IDs follow the pattern: `L{Category}-{Lang}-{Number}` or `L{Category}-{Number}`

### Category Prefixes

| Prefix | Meaning | Examples |
|--------|---------|----------|
| **L1** | Level 1 - Basic hello world | L1-PY-01, L1-PY-02 |
| **L3** | Level 3 - Advanced patterns | L3-PY-03 |
| **LD** | DDS Core - Discovery, types, codegen | LD-01, LD-03, LD-07 |
| **LN** | Native - C/C++ implementations | LN-C-01, LN-CPP-01 |
| **LQ** | QoS - Quality of Service tasks | LQ-01, LQ-02 |
| **LR** | RPC - Request-Reply patterns | LR-01, LR-02 |
| **LX** | Cross - Cross-language interop | LX-CPP-01 |
| **LS** | Security - DDS Security Plugins | LS-01 (proposed) |
| **LB** | Bandwidth - Transport optimization | LB-01 (proposed) |
| **LP** | Persistence - Durability services | LP-01 (proposed) |

### Language Suffixes

| Suffix | Language |
|--------|----------|
| **PY** | Python |
| **C** | C |
| **CPP** | C++ |

## Task Summary

Pass rates calculated across all modern harnesses/models (excluding legacy models like Sonnet 4.0).

| ID | Name | Prompt Summary | Expected Output | Difficulty (Pass Rate) |
|----|------|----------------|-----------------|------------------------|
| L1-PY-01 | Hello Publisher | Create Python publisher, 10 samples to "HelloWorld" topic on domain 85 | Published samples with message + count | Basic (100%) |
| L1-PY-02 | Hello Subscriber | Create Python subscriber using WaitSet, output as JSONL | `{"message":"...", "count":N}` | Basic (93.3%) |
| LD-01 | Content Filtered Topic | Python subscriber filtering sensor data where id>50 AND value>75.0 | JSONL of filtered samples | Basic (86.7%) |
| LD-03 | RTI DDS Gen Workflow | Write IDL, run rtiddsgen, use generated types (not DynamicData) | 10 JSON samples via generated types | Basic (100%) |
| LD-07 | Discovery GUID Mining | (A) Print publisher GUID per sample; (B) Discover subscriber GUIDs via DCPSSubscription | GUIDs extracted from discovery | Advanced (13.3%) |
| LN-C-02 | C Content Filtered Sub | C subscriber with ContentFilteredTopic, CLI args for filter params | Filtered sensor readings as JSON | Hard (33.3%) |
| LN-CPP-01 | Native C++ Publisher | C++ Modern API publisher with RELIABLE/TRANSIENT_LOCAL/KEEP_ALL QoS | 10 samples to HelloWorld topic | Basic (100%) |
| LN-CPP-03 | C++ Content Filtered Sub | C++ subscriber with ContentFilteredTopic for sensor filtering | Filtered sensor readings as JSON | Intermediate (66.7%) |
| LQ-01 | Late Joiner Durability | Fix QoS so late-joining subscriber receives historical samples | All samples received regardless of timing | Intermediate (73.3%) |
| LQ-02 | QoS Mismatch Debug | Debug and fix RxO policy incompatibility between pub/sub | Communication established | Basic (93.3%) |
| LR-01 | DDS RPC Request-Reply | Python RPC client calling Calculator service (add/sub/mul/div) | `{"result":N, "success":true}` | Advanced (13.3%) |
| LX-CPP-01 | Python to C++ Publisher | Translate Python publisher to C++ maintaining interop | C++ pub works with Python sub | Basic (100%) |
| L3-PY-03 | Full Loop Adapter | Binary protocol bridge: inbound (Binary→DDS) + outbound (DDS→Binary) | Two adapter scripts | Hard (40.0%) |

### Difficulty Scale

| Difficulty | Pass Rate | Count |
|------------|-----------|-------|
| **Advanced** | <25% | 2 (LD-07, LR-01) |
| **Hard** | 25-50% | 2 (LN-C-02, L3-PY-03) |
| **Intermediate** | 50-75% | 2 (LN-CPP-03, LQ-01) |
| **Basic** | >75% | 7 (L1-PY-01, L1-PY-02, LD-01, LD-03, LN-CPP-01, LQ-02, LX-CPP-01) |

## Tasks by Difficulty

### Advanced (<25% pass rate) - 2 tasks
- **LD-07** (13.3%): Discovery/GUID mining - only Claude Code Opus/Sonnet pass
- **LR-01** (13.3%): RPC request-reply - only Claude Code Opus/Sonnet pass

### Hard (25-50% pass rate) - 2 tasks
- **LN-C-02** (33.3%): C ContentFilteredTopic with CLI args
- **L3-PY-03** (40.0%): Binary protocol bridge adapters

### Intermediate (50-75% pass rate) - 2 tasks
- **LN-CPP-03** (66.7%): C++ ContentFilteredTopic
- **LQ-01** (73.3%): Late joiner durability debugging

### Basic (>75% pass rate) - 7 tasks
- **L1-PY-01** (100%): Hello World publisher
- **L1-PY-02** (93.3%): Hello World subscriber
- **LD-01** (86.7%): Python ContentFilteredTopic
- **LD-03** (100%): rtiddsgen workflow
- **LN-CPP-01** (100%): Native C++ publisher
- **LQ-02** (93.3%): QoS mismatch debugging
- **LX-CPP-01** (100%): Python to C++ translation

## Benchmark Results (Latest)

**Harnesses matter.** The same model performs differently across harnesses.

### Claude Code: 100% Pass Rate

| Harness + Model | Pass Rate | Notes |
|-----------------|-----------|-------|
| **Claude Code + Opus 4.5** | **13/13 (100%)** | All tasks including LD-07, LR-01 |
| **Claude Code + Sonnet 4.5** | **13/13 (100%)** | All tasks including LD-07, LR-01 |
| Claude Code + Haiku 4.5 | 11/13 (85%) | Fails LD-07, LR-01 |

### Other Harnesses: Varied Results

| Harness + Model | Pass Rate | Fails On |
|-----------------|-----------|----------|
| Cursor + Opus 4.5 | 11/13 (85%) | LD-07, LR-01 |
| Cursor + Sonnet 4.5 | 11/13 (85%) | LD-07, LR-01 |
| Cursor + GPT-5.2 | 9/13 (69%) | LD-07, LR-01, L3-PY-03, LN-C-02 |
| Cursor + Grok 4 | 9/13 (69%) | LD-07, LR-01, L3-PY-03, LN-C-02 |
| Aider + Opus 4.5 | 11/13 (85%) | LD-07, LR-01 |
| Aider + GPT-5.2 | 9/13 (69%) | LD-07, LR-01, L3-PY-03, LN-C-02 |

### Hardest Tasks (Discriminating)

| Task | Claude Code | Cursor | Aider | Codex |
|------|-------------|--------|-------|-------|
| LD-07 (GUID Mining) | ✅ Opus/Sonnet | ❌ All | ❌ All | ❌ All |
| LR-01 (RPC) | ✅ Opus/Sonnet | ❌ All | ❌ All | ❌ All |
| L3-PY-03 (Protocol Bridge) | ✅ All | ✅ Opus/Sonnet | ✅ Opus | ❌ All |
| LN-C-02 (C Content Filter) | ✅ Opus/Sonnet | ✅ Opus/Sonnet | ✅ Opus | ❌ All |

**Key Observations:**
- **Claude Code is the best harness** for DDS tasks - 100% with top models
- **LD-07 and LR-01** are Claude Code exclusive - no other harness passes these
- **Harness > Model**: Opus in Cursor (85%) < Sonnet in Claude Code (100%)
- **GPT-5.2 and Grok** struggle on advanced tasks regardless of harness

---

## Proposed New Tasks (NOT IMPLEMENTED)

These tasks are specified but not yet built. See [ADVANCED_DDS_TASKS_PLAN.md](ADVANCED_DDS_TASKS_PLAN.md) for full details.

| ID | Name | Prompt Summary | Expected Output | Difficulty | Status |
|----|------|----------------|-----------------|------------|--------|
| LD-08 | Topic Query Historical Data | Create C subscriber using Topic Queries to retrieve historical samples from late-join scenario | Distinguish HISTORICAL vs LIVE samples, print counts | Hard | ❌ Not Implemented |
| LP-01 | Persistence Recovery | Create pub/sub with TRANSIENT durability, implement checkpoint/recovery after restart | Recover state from Persistence Service | Hard | ❌ Not Implemented |
| LR-02 | Routing Service Adapter | Create custom Routing Service adapter bridging JSON files to DDS | Adapter library + RS config | Hard | ❌ Not Implemented |
| LS-01 | Participant Banishing | Create security monitor that discovers participants and dynamically revokes access by subject name | Print discovered certs, banish specified participant | Expert | ❌ Not Implemented |
| LB-01 | Bandwidth Optimization | Configure Limited Bandwidth Plugins (LBPDISCOVERY, LBRTPS) for constrained networks | Report compression ratio and discovery stats | Expert | ❌ Not Implemented |

### Proposed Tasks by Category

#### Historical Data & Persistence (2 tasks)
- **LD-08**: Topic Query API for historical sample retrieval
- **LP-01**: Persistence Service integration and state recovery

#### Infrastructure Services (2 tasks)
- **LR-02**: Routing Service custom adapter development
- **LB-01**: Transport plugin configuration for bandwidth optimization

#### Security (1 task)
- **LS-01**: Security Plugins API for dynamic access control

### Implementation Notes

- All proposed tasks require C or C++ (no Python)
- No API hints provided - agents must discover APIs from `$NDDSHOME`
- Data models provided as XML (not IDL) to test format conversion
- Target pass rate: <30% for top-tier agents, <10% for mid-tier

### Spec Locations

| Task | Spec File |
|------|-----------|
| LD-08 | [specs/LD-08_topic_query.md](specs/LD-08_topic_query.md) |
| LP-01 | [specs/LP-01_persistence_recovery.md](specs/LP-01_persistence_recovery.md) |
| LR-02 | [specs/LR-02_routing_service_adapter.md](specs/LR-02_routing_service_adapter.md) |
| LS-01 | [specs/LS-01_participant_banishing.md](specs/LS-01_participant_banishing.md) |
| LB-01 | [specs/LB-01_bandwidth_optimization.md](specs/LB-01_bandwidth_optimization.md) |
