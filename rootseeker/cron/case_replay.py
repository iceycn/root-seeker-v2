from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.evaluation import EvaluationReport
from rootseeker.replay import ReplayRunner, ReplayStore, default_replay_suite

__all__ = ["run_scheduled_replay"]


def run_scheduled_replay(
    repo_root: Path | None = None,
    *,
    suite_name: str = "cron-default-flow",
    repeat_each: int = 1,
) -> EvaluationReport:
    runtime = create_dev_runtime(repo_root or Path.cwd())
    runner = ReplayRunner(runtime, ReplayStore())
    runner.load_cases(default_replay_suite())
    result = runner.run_suite(suite_name=suite_name, repeat_each=repeat_each)
    return result.report
