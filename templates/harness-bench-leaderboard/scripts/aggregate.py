#!/usr/bin/env python3
"""Aggregate results into leaderboards.

Reads individual result files and produces aggregated leaderboards
organized by task, harness, model, and overall ranking.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LeaderboardEntry:
    """A single entry in a leaderboard."""
    task_id: str
    harness_id: str
    model: str | None
    run_id: str
    score: float
    duration_seconds: float
    iterations: int
    evaluated_at: str
    success: bool

    # Rankings (computed)
    rank_overall: int = 0
    rank_in_task: int = 0
    rank_for_harness: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "harness_id": self.harness_id,
            "model": self.model,
            "run_id": self.run_id,
            "score": self.score,
            "duration_seconds": self.duration_seconds,
            "iterations": self.iterations,
            "evaluated_at": self.evaluated_at,
            "success": self.success,
            "rank_overall": self.rank_overall,
            "rank_in_task": self.rank_in_task,
            "rank_for_harness": self.rank_for_harness,
        }


@dataclass
class LeaderboardConfig:
    """Configuration for leaderboard computation."""
    # Scoring weights
    score_weight: float = 0.6
    speed_weight: float = 0.2
    efficiency_weight: float = 0.2

    # Ranking rules
    min_submissions: int = 1
    recent_window_days: int = 30


class LeaderboardAggregator:
    """Aggregates results into leaderboards."""

    def __init__(self, data_dir: Path, config: LeaderboardConfig | None = None):
        self.data_dir = Path(data_dir)
        self.config = config or LeaderboardConfig()
        self.results_dir = self.data_dir / "results"
        self.leaderboards_dir = self.data_dir / "leaderboards"
        self.statistics_dir = self.data_dir / "statistics"

    def aggregate(self) -> None:
        """Run full aggregation."""
        entries = self._load_all_results()

        if not entries:
            print("No results found")
            return

        print(f"Loaded {len(entries)} results")

        # Compute rankings
        self._compute_rankings(entries)

        # Generate leaderboards
        self._generate_overall_leaderboard(entries)
        self._generate_task_leaderboards(entries)
        self._generate_harness_leaderboards(entries)
        self._generate_model_leaderboards(entries)

        # Generate statistics
        self._generate_statistics(entries)

        print("Aggregation complete")

    def _load_all_results(self) -> list[LeaderboardEntry]:
        """Load all result files."""
        entries = []

        for result_file in self.results_dir.rglob("*.json"):
            try:
                data = json.loads(result_file.read_text())
                entry = self._parse_result(data)
                if entry:
                    entries.append(entry)
            except Exception as e:
                print(f"Error loading {result_file}: {e}")

        return entries

    def _parse_result(self, data: dict) -> LeaderboardEntry | None:
        """Parse a result file into a LeaderboardEntry."""
        try:
            metadata = data.get("_metadata", {})
            rubric = data.get("rubric", {})

            return LeaderboardEntry(
                task_id=metadata.get("task_id") or data.get("task_id", ""),
                harness_id=metadata.get("harness_id") or data.get("harness_id", ""),
                model=data.get("model"),
                run_id=metadata.get("run_id") or data.get("run_id", ""),
                score=data.get("score", 0.0),
                duration_seconds=data.get("duration_seconds", 0.0),
                iterations=data.get("iterations", 0),
                evaluated_at=data.get("evaluated_at", ""),
                success=data.get("success", False),
            )
        except Exception:
            return None

    def _compute_rankings(self, entries: list[LeaderboardEntry]) -> None:
        """Compute rankings for all entries."""
        # Sort by score descending
        sorted_entries = sorted(entries, key=lambda e: -e.score)

        # Overall ranking
        for i, entry in enumerate(sorted_entries, 1):
            entry.rank_overall = i

        # Per-task ranking
        task_groups = defaultdict(list)
        for entry in entries:
            task_groups[entry.task_id].append(entry)

        for task_id, task_entries in task_groups.items():
            sorted_task = sorted(task_entries, key=lambda e: -e.score)
            for i, entry in enumerate(sorted_task, 1):
                entry.rank_in_task = i

        # Per-harness ranking
        harness_groups = defaultdict(list)
        for entry in entries:
            harness_groups[entry.harness_id].append(entry)

        for harness_id, harness_entries in harness_groups.items():
            sorted_harness = sorted(harness_entries, key=lambda e: -e.score)
            for i, entry in enumerate(sorted_harness, 1):
                entry.rank_for_harness = i

    def _generate_overall_leaderboard(self, entries: list[LeaderboardEntry]) -> None:
        """Generate overall leaderboard."""
        self.leaderboards_dir.mkdir(parents=True, exist_ok=True)

        # Sort by overall rank
        sorted_entries = sorted(entries, key=lambda e: e.rank_overall)

        leaderboard = {
            "type": "overall",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(sorted_entries),
            "entries": [e.to_dict() for e in sorted_entries[:100]],  # Top 100
        }

        output = self.leaderboards_dir / "overall.json"
        output.write_text(json.dumps(leaderboard, indent=2))
        print(f"Generated: {output}")

    def _generate_task_leaderboards(self, entries: list[LeaderboardEntry]) -> None:
        """Generate per-task leaderboards."""
        task_dir = self.leaderboards_dir / "by-task"
        task_dir.mkdir(parents=True, exist_ok=True)

        task_groups = defaultdict(list)
        for entry in entries:
            task_groups[entry.task_id].append(entry)

        for task_id, task_entries in task_groups.items():
            sorted_entries = sorted(task_entries, key=lambda e: e.rank_in_task)

            leaderboard = {
                "type": "by-task",
                "task_id": task_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(sorted_entries),
                "entries": [e.to_dict() for e in sorted_entries[:50]],
            }

            output = task_dir / f"{task_id}.json"
            output.write_text(json.dumps(leaderboard, indent=2))

        print(f"Generated {len(task_groups)} task leaderboards")

    def _generate_harness_leaderboards(self, entries: list[LeaderboardEntry]) -> None:
        """Generate per-harness leaderboards."""
        harness_dir = self.leaderboards_dir / "by-harness"
        harness_dir.mkdir(parents=True, exist_ok=True)

        harness_groups = defaultdict(list)
        for entry in entries:
            harness_groups[entry.harness_id].append(entry)

        for harness_id, harness_entries in harness_groups.items():
            sorted_entries = sorted(harness_entries, key=lambda e: e.rank_for_harness)

            leaderboard = {
                "type": "by-harness",
                "harness_id": harness_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(sorted_entries),
                "entries": [e.to_dict() for e in sorted_entries[:50]],
            }

            # Sanitize harness ID for filename
            safe_id = harness_id.replace("/", "_")
            output = harness_dir / f"{safe_id}.json"
            output.write_text(json.dumps(leaderboard, indent=2))

        print(f"Generated {len(harness_groups)} harness leaderboards")

    def _generate_model_leaderboards(self, entries: list[LeaderboardEntry]) -> None:
        """Generate per-model leaderboards."""
        model_dir = self.leaderboards_dir / "by-model"
        model_dir.mkdir(parents=True, exist_ok=True)

        model_groups = defaultdict(list)
        for entry in entries:
            if entry.model:
                model_groups[entry.model].append(entry)

        for model, model_entries in model_groups.items():
            sorted_entries = sorted(model_entries, key=lambda e: -e.score)

            # Assign model-specific ranking
            for i, entry in enumerate(sorted_entries, 1):
                pass  # Could add rank_for_model

            leaderboard = {
                "type": "by-model",
                "model": model,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(sorted_entries),
                "entries": [e.to_dict() for e in sorted_entries[:50]],
            }

            # Sanitize model name for filename
            safe_model = model.replace("/", "_").replace(":", "_")
            output = model_dir / f"{safe_model}.json"
            output.write_text(json.dumps(leaderboard, indent=2))

        print(f"Generated {len(model_groups)} model leaderboards")

    def _generate_statistics(self, entries: list[LeaderboardEntry]) -> None:
        """Generate aggregate statistics."""
        self.statistics_dir.mkdir(parents=True, exist_ok=True)

        # Overall stats
        successful = [e for e in entries if e.success]
        scores = [e.score for e in entries]
        durations = [e.duration_seconds for e in entries if e.duration_seconds > 0]

        stats = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_submissions": len(entries),
            "successful_submissions": len(successful),
            "success_rate": len(successful) / len(entries) if entries else 0,
            "score": {
                "mean": sum(scores) / len(scores) if scores else 0,
                "max": max(scores) if scores else 0,
                "min": min(scores) if scores else 0,
            },
            "duration": {
                "mean": sum(durations) / len(durations) if durations else 0,
                "max": max(durations) if durations else 0,
                "min": min(durations) if durations else 0,
            },
            "by_harness": {},
            "by_task": {},
        }

        # Per-harness stats
        harness_groups = defaultdict(list)
        for entry in entries:
            harness_groups[entry.harness_id].append(entry)

        for harness_id, harness_entries in harness_groups.items():
            h_successful = [e for e in harness_entries if e.success]
            h_scores = [e.score for e in harness_entries]
            stats["by_harness"][harness_id] = {
                "submissions": len(harness_entries),
                "success_rate": len(h_successful) / len(harness_entries),
                "mean_score": sum(h_scores) / len(h_scores),
            }

        # Per-task stats
        task_groups = defaultdict(list)
        for entry in entries:
            task_groups[entry.task_id].append(entry)

        for task_id, task_entries in task_groups.items():
            t_successful = [e for e in task_entries if e.success]
            t_scores = [e.score for e in task_entries]
            stats["by_task"][task_id] = {
                "submissions": len(task_entries),
                "success_rate": len(t_successful) / len(task_entries),
                "mean_score": sum(t_scores) / len(t_scores),
            }

        output = self.statistics_dir / "summary.json"
        output.write_text(json.dumps(stats, indent=2))
        print(f"Generated: {output}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Aggregate leaderboards")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    args = parser.parse_args()

    aggregator = LeaderboardAggregator(Path(args.data_dir))
    aggregator.aggregate()


if __name__ == "__main__":
    main()
