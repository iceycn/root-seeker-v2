"""Tests for worker entrypoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.worker.main import _seed_demo_task, main, run_loop, run_once


class TestWorkerMain:
    """Tests for worker main entrypoint."""

    def test_main_without_loop(self) -> None:
        """Test worker runs once without --loop flag."""
        with patch("apps.worker.main.run_once") as mock_run_once:
            mock_run_once.return_value = 0
            result = main([])
            mock_run_once.assert_called_once()
            assert result == 0

    def test_main_with_loop(self) -> None:
        """Test worker runs loop with --loop flag."""
        with patch("apps.worker.main.run_loop") as mock_run_loop:
            mock_run_loop.return_value = 0
            result = main(["--loop", "--max-runs", "1"])
            mock_run_loop.assert_called_once()
            assert result == 0

    def test_main_loop_with_custom_params(self) -> None:
        """Test worker loop with custom parameters."""
        with patch("apps.worker.main.run_loop") as mock_run_loop:
            mock_run_loop.return_value = 0
            result = main([
                "--loop",
                "--interval-seconds", "1.0",
                "--max-empty-polls", "3",
                "--max-runs", "10",
            ])
            mock_run_loop.assert_called_once_with(
                repo_root=Path.cwd(),
                interval_seconds=1.0,
                max_empty_polls=3,
                max_runs=10,
                seed_demo=False,
            )
            assert result == 0


class TestRunOnce:
    """Tests for run_once function."""

    def test_run_once_success(self, tmp_path: Path) -> None:
        """Test successful single run."""
        with patch("apps.worker.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.worker.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_task = MagicMock()
                mock_task.task_id = "task-123"
                mock_task.status.value = "completed"
                mock_task.result_ref = "case-456"
                mock_task_runtime.run_once.return_value = mock_task

                result = run_once(tmp_path)

                assert result == 0
                mock_task_runtime.run_once.assert_called_once()

    def test_run_once_no_task(self, tmp_path: Path) -> None:
        """Test run once with no task."""
        with patch("apps.worker.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.worker.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime
                mock_task_runtime.run_once.return_value = None

                result = run_once(tmp_path)

                assert result == 1


class TestRunLoop:
    """Tests for run_loop function."""

    def test_run_loop_max_empty_polls(self, tmp_path: Path) -> None:
        """Test loop stops after max empty polls."""
        with patch("apps.worker.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.worker.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime
                mock_task_runtime.run_once.return_value = None

                with patch("apps.worker.main.time.sleep"):
                    result = run_loop(
                        repo_root=tmp_path,
                        interval_seconds=0.1,
                        max_empty_polls=2,
                        max_runs=10,
                    )

                    assert result == 0

    def test_run_loop_task_failure(self, tmp_path: Path) -> None:
        """Test loop returns error on task failure."""
        with patch("apps.worker.main.create_dev_runtime") as mock_runtime:
            mock_rt = MagicMock()
            mock_runtime.return_value = mock_rt

            with patch("apps.worker.main.TaskRuntime") as mock_task_rt:
                mock_task_runtime = MagicMock()
                mock_task_rt.return_value = mock_task_runtime

                mock_task = MagicMock()
                mock_task.task_id = "task-123"
                mock_task.status.value = "failed"
                mock_task.result_ref = None
                mock_task_runtime.run_once.return_value = mock_task

                with patch("apps.worker.main.time.sleep"):
                    result = run_loop(
                        repo_root=tmp_path,
                        interval_seconds=0.1,
                        max_empty_polls=5,
                        max_runs=10,
                    )

                    assert result == 1


class TestSeedDemoTask:
    """Tests for _seed_demo_task function."""

    def test_seed_demo_task(self) -> None:
        """Test demo task seeding."""
        mock_task_runtime = MagicMock()
        _seed_demo_task(mock_task_runtime)

        mock_task_runtime.submit.assert_called_once()
        call_args = mock_task_runtime.submit.call_args
        assert call_args.kwargs["kind"].value == "case_run"
        assert "title" in call_args.kwargs["payload"]
        assert call_args.kwargs["payload"]["service_name"] == "order-service"
