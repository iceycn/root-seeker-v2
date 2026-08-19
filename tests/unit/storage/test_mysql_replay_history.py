from __future__ import annotations

from contextlib import contextmanager

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot
from rootseeker.storage.mysql_conn import MysqlConnectConfig
from rootseeker.storage.mysql_replay_history import MysqlReplayHistoryStore


def test_mysql_replay_history_store_roundtrip_with_mock_connection(monkeypatch) -> None:
    cases: dict[str, str] = {}
    runs: dict[str, tuple[str, str]] = {}

    class _Cursor:
        def execute(self, sql: str, params: tuple | None = None) -> None:
            self._sql = sql
            self._params = params or ()
            if "CREATE TABLE" in sql:
                return
            if "REPLACE INTO replay_history_cases" in sql:
                cases[self._params[0]] = self._params[1]
            elif "REPLACE INTO replay_history_runs" in sql:
                runs[self._params[0]] = (self._params[1], self._params[2])

        def fetchall(self) -> list[tuple]:
            if "FROM replay_history_cases" in self._sql:
                return [(value,) for value in cases.values()]
            if "FROM replay_history_runs" in self._sql:
                return [(replay_id, data) for replay_id, data in runs.values()]
            return []

        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _Conn:
        def cursor(self) -> _Cursor:
            return _Cursor()

        def __enter__(self) -> _Conn:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    @contextmanager
    def _fake_mysql_connection(_config):
        yield _Conn()

    monkeypatch.setattr(
        "rootseeker.storage.mysql_replay_history.mysql_connection",
        _fake_mysql_connection,
    )

    case = ReplayCaseSpec(
        replay_id="rp-mysql-1",
        name="mysql replay",
        alert_payload={"title": "t", "service_name": "svc"},
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="unit",
        ),
    )
    run = ReplayRunSnapshot(
        replay_id="rp-mysql-1",
        run_id="run-mysql-1",
        case_id="case-1",
        skill_name="default-log-triage",
        flow_plugin_id="builtin.default_log_triage_flow",
        passed=True,
        metrics={"duration_ms": 1.0},
    )

    first = MysqlReplayHistoryStore(MysqlConnectConfig())
    first.upsert_case(case)
    first.add_run(run)

    second = MysqlReplayHistoryStore(MysqlConnectConfig())

    assert second.get_case("rp-mysql-1") is not None
    assert len(second.get_runs("rp-mysql-1")) == 1
