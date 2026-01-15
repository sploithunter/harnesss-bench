"""Task management for Harness Bench."""

from .task import Task, TaskConfig
from .workspace import WorkspaceManager
from .registry import TaskRegistry, LocalTaskRegistry, TaskEntry, TaskIndex

__all__ = [
    "Task",
    "TaskConfig",
    "WorkspaceManager",
    "TaskRegistry",
    "LocalTaskRegistry",
    "TaskEntry",
    "TaskIndex",
]
