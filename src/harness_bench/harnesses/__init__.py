"""Harness bridge implementations.

This module contains official bridge implementations for various
AI coding assistants. Third parties can also implement their own
bridges by subclassing HarnessBridge.
"""

from .aider import AiderBridge
from .claude_code import ClaudeCodeBridge
from .codex import CodexBridge

__all__ = [
    "AiderBridge",
    "ClaudeCodeBridge",
    "CodexBridge",
]
