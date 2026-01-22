# Harness Bench Progress

Last updated: 2026-01-22

## Recent Changes (Jan 22, 2026)

### Consistent JSON Output Across All Harnesses
All harness bridges now produce identical JSON structure for fair comparison:

**Turn 0 (Instructions):**
- `turn`, `role`, `source`, `content`, `initial_files`

**Turn 1+ (Coder Response):**
- `turn`, `role`, `harness_output`, `iteration_cost_usd`, `elapsed_seconds`
- `files_created`, `files_modified`, `files_unchanged` (file provenance tracking)
- `test_results`

### File Provenance Tracking
Every result now tracks which files were:
- **initial_files**: Files present before model runs (provided by task/harness)
- **files_created**: New files created by the model
- **files_modified**: Existing files changed by the model
- **files_unchanged**: Original files left as-is

### New Features
- `--no-append-prompt` flag for A/B testing subscription harness
- `expand_claude_model_id()` for full model names in results
- Test script: `scripts/test_harness_logging.py` for cross-harness comparison

### Model Documentation
Added comprehensive model version table to CLAUDE.md:
- Anthropic: claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5
- OpenAI: gpt-5.2, o3, o3-mini, o4-mini
- Google: gemini-2.5-pro, gemini-2.5-flash

Files modified:
- `src/harness_bench/harnesses/ralph_base.py` - Base class with result tracking
- `src/harness_bench/harnesses/claude_code.py` - Fixed subscription bridge
- `src/harness_bench/harnesses/aider.py` - Response capture
- `src/harness_bench/harnesses/codex.py` - Response capture
- `src/harness_bench/harnesses/cursor.py` - Response capture
- `scripts/test_harness_logging.py` - New test script
- `scripts/run_dds_benchmark.py` - Added --no-append-prompt flag
- `CLAUDE.md` - Model documentation

## Current State

### Results Organization
Results are now organized in a clean directory structure:
```
results/harness/{harness}/{model}/{task}.json
```

Example:
```
results/harness/
├── aider/
│   ├── opus-4.5/
│   │   ├── L1-PY-01.json
│   │   └── archive/
│   └── gpt-5.2/
├── claude-code/
│   ├── opus-4.5/
│   └── sonnet-4.5/
├── codex/
│   └── gpt-5.2/
└── cursor/
    ├── gpt-5.2/
    └── opus-4.5/
```

### Key Scripts
- `scripts/migrate_to_new_structure.py` - Migrate scattered results to new structure
- `scripts/extract_all_results.py` - Extract and consolidate results for charting
- `scripts/run_dds_benchmark.py` - Run full benchmark suite
- `results/generate_charts.py` - Generate visualization charts

### Canonical 13 Tasks
```
L1-PY-01_hello_publisher
L1-PY-02_hello_subscriber
L3-PY-03_full_loop_adapter
LD-01_content_filtered_topic
LD-03_rtiddsgen_workflow
LD-07_discovery_guid_mining
LN-CPP-01_native_cpp_publisher
LQ-01_late_joiner_durability
LX-CPP-01_python_to_cpp_publisher
LQ-02_qos_mismatch_debug
LR-01_dds_rpc_request_reply
LN-CPP-03_content_filtered_subscriber
LN-C-02_content_filtered_subscriber
```

## Recent Changes (Jan 16, 2026)

### Benchmark Completion Status

| Harness | Model | Tests | Status |
|---------|-------|-------|--------|
| claude-code | opus-4.5 | 13/13 | ✅ Complete |
| claude-code | sonnet-4.5 | 13/13 | ✅ Complete |
| claude-code | haiku-4.5 | 13/13 | ✅ Complete |
| aider | opus-4.5 | 13/13 | ✅ Complete |
| aider | gpt-5.2 | 13/13 | ✅ Complete |
| aider | gemini-3-pro | 13/13 | ✅ Complete |
| aider | grok-4 | 13/13 | ✅ Complete |
| codex | gpt-5.2 | 13/13 | ✅ Complete |
| codex | gpt-5.2-codex | 13/13 | ✅ Complete |
| cursor | all models | 9/13 | ⚠️ Blocked by CLI bug |

**Cursor blocked tests:** LN-C-02, LN-CPP-03, LQ-02, LR-01 (4 tests across 6 models)

### Logging Updates - COMPLETED
All harness bridges now capture full conversation logs for debugging failures:

| Harness | Log File | Format |
|---------|----------|--------|
| Claude Code | `.claude_conversation_iter{N}.jsonl` | stream-json with --verbose |
| Cursor | `.cursor_conversation_iter{N}.json` | JSON output |
| Codex | `.codex_conversation_iter{N}.jsonl` | JSONL events |
| Aider | `.aider.chat.history.md` | Already had this |

Files modified:
- `src/harness_bench/harnesses/claude_code.py` - Added stream-json logging with real-time flush
- `src/harness_bench/harnesses/cursor.py` - Added JSON output saving
- `src/harness_bench/harnesses/codex.py` - Added JSONL output saving

### Logging Verification
- **Claude Code**: ✅ Verified working (creates jsonl files)
- **Codex**: ✅ Verified working (creates jsonl with reasoning blocks)
- **Cursor**: ⚠️ Code is correct but blocked by `cursor-agent` CLI bugs

#### Cursor CLI Status (Jan 16, 2026)
The `cursor-agent` CLI has known bugs with headless/print mode:
- `cursor-agent -p` fails silently with exit code 1
- Process hangs after task completion in some cases
- Auth works fine (`cursor-agent status` shows logged in)
- Model listing works (`cursor-agent --list-models`)

**References:**
- https://github.com/cursor/cursor/issues/3588
- https://forum.cursor.com/t/cursor-cli-execute-no-stop/148922

The harness logging code is implemented and ready - it will work once Cursor fixes the CLI.

## Environment Setup

### Required Environment Variables
```bash
export ANTHROPIC_API_KEY=...      # For Claude Code
export OPENAI_API_KEY=...         # For Codex, Aider with OpenAI models
export CURSOR_API_KEY=...         # For Cursor harness
```

### Model Names
When using harnesses directly:
- **Claude Code CLI**: Use `claude-sonnet-4-5-20250929` (NOT `anthropic/claude-sonnet-4-5-20250929`)
- **Aider**: Use `anthropic/claude-sonnet-4-5-20250929` or `openai/gpt-5.2`
- **Codex**: Use `gpt-5.2` or `o3-mini`
- **Cursor**: Use `gpt-5.2`, `opus-4.5`, etc.

## Next Steps / TODO
1. ~~Run Cursor tests with API key configured~~ → Blocked by cursor-agent CLI bugs
2. Consider running benchmarks with new logging to build up failure analysis data
3. Clean up old scattered JSON files in results/ root (already migrated)
4. Monitor cursor-agent CLI updates for headless mode fixes

## Quick Commands

```bash
# Regenerate results summary
python scripts/extract_all_results.py

# Generate charts
python results/generate_charts.py

# Run single harness benchmark
python scripts/run_dds_benchmark.py --harness codex --model gpt-5.2

# View a conversation log (example)
cat workspaces/*/.claude_conversation_iter1.jsonl | jq .
```
