from pathlib import Path

from rootseeker.cli_commands.commands.replay import run_replay_command
from rootseeker.cron.case_replay import run_scheduled_replay


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_cli_replay_command_returns_exit_code() -> None:
    code = run_replay_command(_repo_root())
    assert code in (0, 2)


def test_cron_replay_job_returns_report() -> None:
    report = run_scheduled_replay(_repo_root())
    assert report.suite_name == "cron-default-flow"
    assert report.case_count > 0
    assert isinstance(report.gate_passed, bool)
