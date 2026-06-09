from apps.cli.main import main as cli_main
from apps.scheduler.main import main as scheduler_main
from apps.worker.main import main as worker_main


def test_cli_demo_command() -> None:
    code = cli_main(["demo"])
    assert code == 0


def test_cli_resume_command_with_missing_checkpoint_returns_failure() -> None:
    code = cli_main(
        [
            "resume",
            "--flow-run-id",
            "missing-flow-run",
            "--title",
            "resume",
            "--symptom",
            "timeout",
            "--service-name",
            "order-service",
            "--trace-id",
            "trace-cli-resume-test",
        ]
    )
    assert code == 2


def test_cli_resume_list_command() -> None:
    code = cli_main(["resume-list"])
    assert code == 0


def test_worker_single_run_command() -> None:
    code = worker_main(["--seed-demo"])
    assert code == 0


def test_worker_single_run_without_seed_returns_no_task() -> None:
    code = worker_main([])
    assert code == 1


def test_worker_loop_command() -> None:
    code = worker_main(["--loop", "--interval-seconds", "0.1", "--max-empty-polls", "1", "--max-runs", "1"])
    assert code == 0


def test_scheduler_single_run_command(tmp_path) -> None:
    code = scheduler_main(["--repeat-each", "1", "--state-path", str(tmp_path / "cron-state.json")])
    assert code in (0, 2)


def test_scheduler_loop_command(tmp_path) -> None:
    code = scheduler_main(
        [
            "--loop",
            "--interval-seconds",
            "0.1",
            "--max-runs",
            "1",
            "--state-path",
            str(tmp_path / "cron-state.json"),
            "--retries",
            "1",
            "--retry-delay-seconds",
            "0.1",
        ]
    )
    assert code == 0
