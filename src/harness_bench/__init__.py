"""Harness Bench - Universal benchmarking framework for AI coding assistants."""

__version__ = "0.1.0"

from .core.manifest import Manifest, HarnessInfo, TaskInfo, RunInfo
from .core.protocol import ProtocolVersion
from .core.bridge import HarnessBridge
from .evaluation.evaluator import Evaluator, EvaluationResult

__all__ = [
    "Manifest",
    "HarnessInfo",
    "TaskInfo",
    "RunInfo",
    "ProtocolVersion",
    "HarnessBridge",
    "Evaluator",
    "EvaluationResult",
]
