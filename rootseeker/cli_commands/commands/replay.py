from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.replay import ReplayRunner, ReplayStore, default_replay_suite

__all__ = ["run_replay_command"]


def run_replay_command(repo_root: Path | None = None) -> int:
    runtime = create_dev_runtime(repo_root or Path.cwd())
    runner = ReplayRunner(runtime, ReplayStore())
    runner.load_cases(default_replay_suite())
    result = runner.run_suite(suite_name="cli-default-flow", repeat_each=1)
    return 0 if result.report.gate_passed else 2
