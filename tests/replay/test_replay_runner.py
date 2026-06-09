from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.evaluation import QualityGatePolicy
from rootseeker.replay import ReplayRunner, ReplayStore, default_replay_suite


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_default_replay_suite_has_required_cases() -> None:
    suite = default_replay_suite()
    assert len(suite) >= 10
    assert all(case.redacted for case in suite)
    assert all(case.human_root_cause for case in suite)


def test_replay_runner_full_suite_and_gate() -> None:
    runtime = create_dev_runtime(_repo_root())
    store = ReplayStore()
    runner = ReplayRunner(runtime, store)
    runner.load_cases(default_replay_suite())
    result = runner.run_suite(suite_name="default-flow-base", repeat_each=2)

    assert result.report.case_count >= 10
    assert result.report.aggregate_metrics
    assert len(result.snapshots) == result.report.case_count * 2
    assert len(result.traces) == len(result.snapshots)
    assert "service_accuracy" in result.report.aggregate_metrics
    assert "tool_fail_rate" in result.report.aggregate_metrics
    assert result.report.gate_policy_name == "default-release"
    assert isinstance(result.report.release_allowed, bool)
    # Ensure history comparison is possible (multiple runs per replay_id)
    rp1_runs = store.get_runs("rp-001")
    assert len(rp1_runs) == 2


def test_replay_runner_accepts_custom_quality_policy() -> None:
    runtime = create_dev_runtime(_repo_root())
    runner = ReplayRunner(
        runtime,
        ReplayStore(),
        gate_policy=QualityGatePolicy(
            name="unit-advisory",
            min_thresholds={"service_accuracy": 2.0},
            max_thresholds={},
            blocking=False,
        ),
    )
    runner.load_cases(default_replay_suite()[:1])
    result = runner.run_suite(suite_name="custom-policy")
    assert result.report.gate_policy_name == "unit-advisory"
    assert result.report.gate_passed is False
    assert result.report.release_allowed is True
