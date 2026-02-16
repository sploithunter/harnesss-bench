# Linux METR Evaluation Environment Spec

**Status:** Deferred - To be implemented later
**Created:** 2025-01-23

## Overview

Run full METR task evaluations with automated scoring on a Linux environment. This enables long-horizon tasks (5-15+ hours) with proper scoring that requires Linux binaries.

## Why Linux?

METR tasks expect:
- `/home/agent/` workspace path
- Linux ELF binaries (e.g., cowthello's `ai_random`, `ai_simple`, `ai_advanced`)
- Scoring scripts that call these binaries via subprocess

Claude Code OAuth requires a browser, which rules out headless Docker. Running on Linux (bare metal or VM) allows browser-based OAuth while keeping native task compatibility.

## Hardware Requirements

### Minimum (VM)
- 4 CPU cores
- 16GB RAM
- 100GB SSD
- Ubuntu 22.04 or 24.04 LTS

### Recommended (for long-horizon tasks)
- 8+ CPU cores
- 32GB RAM
- 256GB SSD
- GPU optional (for ML tasks like mlab/*)

## Software Requirements

### Base System
```bash
# Ubuntu 22.04/24.04 LTS
sudo apt update && sudo apt upgrade -y

# Essential tools
sudo apt install -y \
    git \
    curl \
    wget \
    build-essential \
    tmux \
    python3 \
    python3-pip \
    python3-venv
```

### Node.js (for Claude Code + CAB)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Claude Code CLI
```bash
npm install -g @anthropic-ai/claude-code
```

### coding-agent-bridge
```bash
git clone https://github.com/anthropics/coding-agent-bridge.git
cd coding-agent-bridge
npm install
npm run build

# Setup hooks
./bin/coding-agent-bridge setup

# Start server (port 4004 to avoid conflicts)
./bin/coding-agent-bridge server --port 4004
```

### harness-bench
```bash
git clone https://github.com/your-org/harness-bench.git
cd harness-bench
pip install -e ".[all]"
```

### METR Dependencies
```bash
# DVC for fetching task binaries
pip install dvc dvc-gs  # or dvc-s3 depending on storage

# Task-specific dependencies
pip install PyPDF2 beautifulsoup4 numpy scipy sympy
```

## Directory Structure

```
/home/agent/                    # METR workspace (create user 'agent')
├── task files copied here

/root/                          # Scoring scripts (need root access)
├── measure.py
├── ai_random
├── ai_simple
└── ai_advanced

/opt/harness-bench/             # harness-bench installation
/opt/coding-agent-bridge/       # CAB installation
```

## One-Time Setup

### 1. Create agent user
```bash
sudo useradd -m -s /bin/bash agent
sudo usermod -aG sudo agent  # Optional, for tasks needing sudo
```

### 2. Claude Code OAuth
```bash
# Need desktop environment or X11 forwarding for browser
claude

# Browser opens, complete OAuth
# Credentials stored in ~/.claude/
```

### 3. Configure Claude hooks
```bash
# ~/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [...],
    "PostToolUse": [...],
    "Stop": [...],
    ...
  }
}
```

### 4. Fetch METR task binaries
```bash
cd /opt/harness-bench/vendor/public-tasks/cowthello/assets/with_source_code
dvc pull hard.dvc
dvc pull smoothened.dvc
```

## Running Evaluations

### Start CAB server
```bash
cd /opt/coding-agent-bridge
./bin/coding-agent-bridge server --port 4004 &
```

### Run a task
```bash
cd /opt/harness-bench

# Using CAB bridge
python -m harness_bench.cli run \
    --task metr-cowthello-main \
    --harness cab \
    --timeout 21600  # 6 hours for long tasks
```

## Tasks Available After Setup

| Task Family | Tasks | Human Time | Scoring |
|-------------|-------|------------|---------|
| cowthello | main, no_internet | 5-15 hrs | Linux binaries |
| debug_small_libs | markdown, orm_allbugs, orm_somebugs | 1.5 hrs | pytest |
| symbolic_regression | level_1, level_2 | 0.5-1.5 hrs | Math eval |
| local_research | 10+ variants | 2-30 min | String match |
| password_check | 1-10 | 10-30 min | Binary check |

## Cloud VM Options

### AWS EC2
- Instance: `t3.xlarge` (4 vCPU, 16GB) or `m5.2xlarge` (8 vCPU, 32GB)
- AMI: Ubuntu 22.04 LTS
- Storage: 100GB gp3
- Estimated cost: ~$0.17-0.38/hr

### GCP Compute Engine
- Machine type: `e2-standard-4` or `e2-standard-8`
- Image: Ubuntu 22.04 LTS
- Estimated cost: ~$0.13-0.27/hr

### Azure VM
- Size: `Standard_D4s_v3` or `Standard_D8s_v3`
- Image: Ubuntu 22.04 LTS
- Estimated cost: ~$0.19-0.38/hr

## Notes

- OAuth tokens persist in `~/.claude/` - VM can run headless after initial auth
- For CI/CD, would need API key (expensive) or token refresh mechanism
- Consider VM snapshots after setup for quick recovery
- tmux sessions persist across SSH disconnects

## Related Files

- `src/harness_bench/harnesses/cab_bridge.py` - CAB harness integration
- `src/harness_bench/metr/task_loader.py` - METR task loading
- `vendor/public-tasks/` - METR task definitions
- `vendor/task-standard/` - METR container spec (reference)
