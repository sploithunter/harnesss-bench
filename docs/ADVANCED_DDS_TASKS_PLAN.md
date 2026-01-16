# Advanced DDS Benchmark Tasks - Implementation Plan

This document outlines 5 new advanced DDS benchmark tasks based on complex examples from the RTI Connext DDS installation (`$NDDSHOME`). These tasks target expert-level DDS functionality that current AI coding agents struggle with.

## Overview

| Task ID | Name | Source Example | Difficulty | Language |
|---------|------|----------------|------------|----------|
| LS-01 | Participant Banishing | `hello_banish` | Expert | C |
| LB-01 | Bandwidth Optimization | `limited_bandwidth_plugins` | Expert | C/C++ |
| LR-02 | Routing Service Adapter | `routing_service/adapters` | Hard | C++ |
| LP-01 | Persistence Recovery | `persistence_service` | Hard | C |
| LD-08 | Topic Query Historical Data | `hello_world_topic_query` | Hard | C |

## Rationale

Current benchmark results show:
- **LD-07 (GUID Mining)**: Only Claude Opus 4.5 and Sonnet 4.5 pass (~15% overall pass rate)
- **LR-01 (RPC Request-Reply)**: 0% pass rate across all agents
- **L3-PY-03 (Full Loop Adapter)**: Only Claude Code passes

These new tasks target areas where even top-performing agents fail:
1. **Security APIs** - Rarely documented, complex certificate handling
2. **Network optimization** - Custom transport plugins, compression
3. **Service integration** - Routing Service, Persistence Service APIs
4. **Historical data patterns** - Topic Queries, TRANSIENT_LOCAL durability

## Implementation Priority

### Phase 1: High Value (Implement First)
1. **LD-08_topic_query** - Builds on existing durability knowledge, clear success criteria
2. **LP-01_persistence_recovery** - Tests state management across restarts

### Phase 2: Security Focus
3. **LS-01_participant_banishing** - Requires Security Plugins, certificate setup

### Phase 3: Infrastructure
4. **LR-02_routing_service_adapter** - Requires Routing Service installation
5. **LB-01_bandwidth_optimization** - Complex multi-file implementation

## Task Design Philosophy

**These tasks test the AI's ability to discover and use DDS APIs, not follow templates.**

### Minimal Scaffolding
- **DO NOT** provide detailed API hints or function names
- **DO NOT** provide complete QoS XML configurations
- **DO NOT** provide Makefiles or CMakeLists.txt
- **DO NOT** provide IDL files (give XML or JSON data models instead)

### What TO Provide
- Clear description of the objective and expected output
- Data model in a different format (XML, JSON) that must be converted
- Verification script and success criteria
- Only the `$NDDSHOME` path as the library root

### Rationale
The goal is to test whether the AI can:
1. Navigate RTI documentation and examples
2. Discover appropriate APIs for the task
3. Convert between data formats (XML → IDL)
4. Create build infrastructure from scratch
5. Debug without hand-holding

Tasks that provide too much scaffolding merely test "can the AI fill in blanks" rather than "can the AI solve novel DDS problems."

## Common Requirements

All tasks require:
- RTI Connext DDS 7.x installation (`$NDDSHOME` set)
- Appropriate license for Security/Routing/Persistence features
- C/C++ compiler (clang or gcc)
- No pre-built templates (agent must create build files)

## Success Metrics

A task is considered appropriately difficult if:
- Pass rate < 30% for top-tier agents (Opus 4.5, GPT-5.2)
- Pass rate < 10% for mid-tier agents (Sonnet, Haiku, Grok)
- Clear, deterministic verification possible
- No ambiguity in requirements

## Individual Task Specifications

Detailed specifications for each task are in:
- [LS-01_participant_banishing.md](specs/LS-01_participant_banishing.md)
- [LB-01_bandwidth_optimization.md](specs/LB-01_bandwidth_optimization.md)
- [LR-02_routing_service_adapter.md](specs/LR-02_routing_service_adapter.md)
- [LP-01_persistence_recovery.md](specs/LP-01_persistence_recovery.md)
- [LD-08_topic_query.md](specs/LD-08_topic_query.md)

## Verification Strategy

Each task uses one or more verification methods:

| Method | Description | Used By |
|--------|-------------|---------|
| Script | Run verify.sh with expected output | All |
| Reference Publisher | Agent's subscriber receives from reference pub | LD-08, LP-01 |
| Reference Subscriber | Agent's publisher sends to reference sub | LR-02, LB-01 |
| State Validation | Check persisted state files | LP-01 |
| Security Log Analysis | Parse security audit logs | LS-01 |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Security Plugins not installed | Check for `libnddssecurity.so` before running |
| License limitations | Document required license features |
| Platform-specific issues | Focus on Linux/macOS, defer Windows |
| Compilation complexity | Provide CMakeLists.txt templates |

## Timeline

| Week | Tasks |
|------|-------|
| 1 | LD-08 implementation + initial testing |
| 2 | LP-01 implementation + LD-08 benchmark run |
| 3 | LS-01 implementation + LP-01 benchmark run |
| 4 | LR-02 + LB-01 implementation |
| 5 | Full benchmark run with all new tasks |

## Notes

- TASK.md should describe objectives, NOT provide API hints
- Data models provided in non-native format (XML instead of IDL)
- Reference implementations are kept in the private `harness-bench-eval` repo
- Task prompts go in public `harness-bench-tasks` repo
- Test with at least 3 different agents before finalizing difficulty rating
- Individual specs contain internal notes (hints sections) that are NOT included in TASK.md
