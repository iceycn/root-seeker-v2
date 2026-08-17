from rootseeker.replay.sample_cases import default_replay_suite
from rootseeker.replay.store import ReplayStore

__all__ = ["ReplayRunner", "ReplayStore", "ReplaySuiteResult", "default_replay_suite"]


def __getattr__(name: str) -> object:
    if name == "ReplayRunner":
        from rootseeker.replay.runner import ReplayRunner

        return ReplayRunner
    if name == "ReplaySuiteResult":
        from rootseeker.replay.runner import ReplaySuiteResult

        return ReplaySuiteResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
