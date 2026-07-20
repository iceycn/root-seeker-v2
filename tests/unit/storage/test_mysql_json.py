from __future__ import annotations

import pytest

from rootseeker.storage.mysql_conn import decode_mysql_json


def test_decode_mysql_json_handles_dict_str_bytes_none() -> None:
    assert decode_mysql_json(None, default=[]) == []
    assert decode_mysql_json({"a": 1}) == {"a": 1}
    assert decode_mysql_json([1, 2]) == [1, 2]
    assert decode_mysql_json('{"a": 1}') == {"a": 1}
    assert decode_mysql_json(b'{"a": 2}') == {"a": 2}
    assert decode_mysql_json("", default={}) == {}


def test_decode_mysql_json_rejects_unexpected_types() -> None:
    with pytest.raises(TypeError):
        decode_mysql_json(123)
