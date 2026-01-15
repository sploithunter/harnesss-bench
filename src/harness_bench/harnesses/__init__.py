"""Harness bridge implementations.

This module contains official bridge implementations for various
AI coding assistants. Third parties can also implement their own
bridges by subclassing HarnessBridge.
"""

from .aider import AiderBridge, AiderRalphLoopBridge
from .claude_code import (
    ClaudeCodeBridge,
    ClaudeCodeDriverBridge,
    ClaudeCodeManualBridge,
    IntelligentDriverBridge,
    RalphLoopBridge,
)
from .codex import CodexBridge
from .cursor import CursorBridge, GenericGUIBridge, PollingBridge, create_gui_bridge

__all__ = [
    "AiderBridge",
    "AiderRalphLoopBridge",
    "ClaudeCodeBridge",
    "ClaudeCodeDriverBridge",
    "ClaudeCodeManualBridge",
    "CodexBridge",
    "CursorBridge",
    "GenericGUIBridge",
    "IntelligentDriverBridge",
    "PollingBridge",
    "RalphLoopBridge",
    "create_gui_bridge",
]
