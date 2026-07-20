from __future__ import annotations

from rootseeker.storage.mysql_conn import MysqlConnectConfig, MysqlConnectionPool


def test_mysql_pool_reuses_connections(monkeypatch) -> None:
    created: list[object] = []

    class _FakeConn:
        def ping(self, reconnect: bool = True) -> None:
            return None

        def close(self) -> None:
            return None

    def _fake_connect(_config: MysqlConnectConfig):
        conn = _FakeConn()
        created.append(conn)
        return conn

    monkeypatch.setattr("rootseeker.storage.mysql_conn.connect_mysql", _fake_connect)
    pool = MysqlConnectionPool(MysqlConnectConfig(pool_size=2))

    first = pool.acquire()
    pool.release(first)
    second = pool.acquire()
    pool.release(second)

    assert first is second
    assert len(created) == 1
