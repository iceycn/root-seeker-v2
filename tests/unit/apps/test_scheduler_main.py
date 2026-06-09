"""Tests for scheduler entrypoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from apps.scheduler.main import main, run_loop, run_once
from rootseeker.cron import JobRunResult, JobRunStatus


def _result(status: JobRunStatus = JobRunStatus.SUCCEEDED) -> JobRunResult:
    return JobRunResult(
        job_id="cron.default-flow-replay",
        status=status,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, tzinfo=UTC),
        message="" if status == JobRunStatus.SUCCEEDED else "quality gate not passed",
        payload={
            "task_id": "task-123",
            "suite_name": "cron-default-flow",
            "gate_passed": status == JobRunStatus.SUCCEEDED,
            "case_count": 5,
        },
    )


class TestSchedulerMain:
    """Tests for scheduler main entrypoint."""

    def test_main_without_loop(self) -> None:
        """Test scheduler runs once without --loop flag."""
        with patch("apps.scheduler.main.run_once") as mock_run_once:
            mock_run_once.return_value = 0
            result = main([])
            mock_run_once.assert_called_once()
            assert result == 0

    def test_main_with_loop(self) -> None:
        """Test scheduler runs loop with --loop flag."""
        with patch("apps.scheduler.main.run_loop") as mock_run_loop:
            mock_run_loop.return_value = 0
            result = main(["--loop", "--max-runs", "1"])
            mock_run_loop.assert_called_once()
            assert result == 0

    def test_main_with_custom_params(self) -> None:
        """Test scheduler with custom parameters."""
        with patch("apps.scheduler.main.run_once") as mock_run_once:
            mock_run_once.return_value = 0
            result = main([
                "--suite-name", "custom-suite",
                "--repeat-each", "3",
            ])
            mock_run_once.assert_called_once_with(
                suite_name="custom-suite",
                repeat_each=3,
                schedule="@hourly",
                timezone="UTC",
                state_path=None,
                run_immediately=True,
            )
            assert result == 0


class TestRunOnce:
    """Tests for run_once function."""

    def test_run_once_success(self, tmp_path) -> None:
        """Test successful single run with gate passed."""
        with patch("apps.scheduler.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.scheduler.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_submitted_task = MagicMock()
                mock_submitted_task.task_id = "task-123"
                mock_task_runtime.submit.return_value = mock_submitted_task

                mock_executed = MagicMock()
                mock_executed.task_id = "task-123"
                mock_executed.status.value = "completed"
                mock_executed.payload = {
                    "report_suite_name": "cron-default-flow",
                    "report_gate_passed": True,
                    "report_case_count": 5,
                }
                mock_task_runtime.run_once.return_value = mock_executed

                result = run_once(state_path=tmp_path / "cron-state.json")

                assert result == 0
                mock_task_runtime.submit.assert_called_once()

    def test_run_once_no_task_executed(self, tmp_path) -> None:
        """Test run once when no task is executed."""
        with patch("apps.scheduler.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.scheduler.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_submitted_task = MagicMock()
                mock_submitted_task.task_id = "task-123"
                mock_task_runtime.submit.return_value = mock_submitted_task
                mock_task_runtime.run_once.return_value = None

                result = run_once(state_path=tmp_path / "cron-state.json")

                assert result == 2

    def test_run_once_gate_not_passed(self, tmp_path) -> None:
        """Test run once when quality gate not passed."""
        with patch("apps.scheduler.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.scheduler.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_submitted_task = MagicMock()
                mock_submitted_task.task_id = "task-123"
                mock_task_runtime.submit.return_value = mock_submitted_task

                mock_executed = MagicMock()
                mock_executed.task_id = "task-123"
                mock_executed.status.value = "completed"
                mock_executed.payload = {
                    "report_suite_name": "cron-default-flow",
                    "report_gate_passed": False,
                    "report_case_count": 5,
                }
                mock_task_runtime.run_once.return_value = mock_executed

                result = run_once(state_path=tmp_path / "cron-state.json")

                assert result == 2

    def test_run_once_task_failed(self, tmp_path) -> None:
        """Test run once when task failed."""
        with patch("apps.scheduler.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.scheduler.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_submitted_task = MagicMock()
                mock_submitted_task.task_id = "task-123"
                mock_task_runtime.submit.return_value = mock_submitted_task

                mock_executed = MagicMock()
                mock_executed.task_id = "task-123"
                mock_executed.status.value = "failed"
                mock_executed.payload = {}
                mock_task_runtime.run_once.return_value = mock_executed

                result = run_once(state_path=tmp_path / "cron-state.json")

                assert result == 2


class TestRunLoop:
    """Tests for run_loop function."""

    def test_run_loop_max_runs(self) -> None:
        """Test loop stops after max runs."""
        with patch("apps.scheduler.main._run_scheduler_tick") as mock_tick:
            mock_tick.return_value = [_result()]

            with patch("apps.scheduler.main.time.sleep"):
                result = run_loop(
                    suite_name="test-suite",
                    repeat_each=1,
                    interval_seconds=0.1,
                    max_runs=2,
                    retries=1,
                    retry_delay_seconds=0.1,
                )

                assert result == 0
                assert mock_tick.call_count == 2

    def test_run_loop_with_retry_success(self) -> None:
        """Test loop retries on failure and succeeds."""
        call_count = 0

        def side_effect(**kwargs) -> list[JobRunResult]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first attempt failed")
            return [_result()]

        with patch("apps.scheduler.main._run_scheduler_tick", side_effect=side_effect):
            with patch("apps.scheduler.main.time.sleep"):
                result = run_loop(
                    suite_name="test-suite",
                    repeat_each=1,
                    interval_seconds=0.1,
                    max_runs=1,
                    retries=2,
                    retry_delay_seconds=0.1,
                )

                assert result == 0

    def test_run_loop_exceeds_retries(self) -> None:
        """Test loop fails after exceeding retries."""

        def side_effect(**kwargs) -> list[JobRunResult]:
            raise RuntimeError("always fails")

        with patch("apps.scheduler.main._run_scheduler_tick", side_effect=side_effect):
            with patch("apps.scheduler.main.time.sleep"):
                result = run_loop(
                    suite_name="test-suite",
                    repeat_each=1,
                    interval_seconds=0.1,
                    max_runs=1,
                    retries=1,
                    retry_delay_seconds=0.1,
                )

                assert result == 2

    def test_run_loop_gate_not_passed_continues(self) -> None:
        """Test loop continues when gate not passed."""
        with patch("apps.scheduler.main._run_scheduler_tick") as mock_tick:
            mock_tick.return_value = [_result(JobRunStatus.FAILED)]

            with patch("apps.scheduler.main.time.sleep"):
                result = run_loop(
                    suite_name="test-suite",
                    repeat_each=1,
                    interval_seconds=0.1,
                    max_runs=2,
                    retries=1,
                    retry_delay_seconds=0.1,
                )

                # Should return 0 even if gate not passed (loop continues)
                assert result == 0
                assert mock_tick.call_count == 2
