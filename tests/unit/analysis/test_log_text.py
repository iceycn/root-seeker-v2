from __future__ import annotations

import json

from rootseeker.analysis.log_text import unwrap_embedded_log_text

_INNER_LOG = (
    "2026-09-03 21:05:01.639 third-ability-service [SOFA-SEV-BOLT-BIZ-12200-10-T20] INFO  "
    "c.c.t.s.i.HarvardManageMentorCourseImpl - harvard manage mentor getCourses error\n"
    "java.lang.NumberFormatException: For input string: \"user@example.com\"\n"
    "\tat com.coolcollege.thirdability.service.impl.HarvardManageMentorCourseImpl"
    ".getCourseProgress(HarvardManageMentorCourseImpl.java:169)\n"
)


def test_unwrap_embedded_log_text_from_sls_content_json() -> None:
    wrapped = json.dumps({"content": _INNER_LOG})
    unwrapped = unwrap_embedded_log_text(wrapped)
    assert unwrapped.startswith("2026-09-03 21:05:01.639 third-ability-service")
    assert "NumberFormatException" in unwrapped
    assert "HarvardManageMentorCourseImpl.java:169" in unwrapped
    assert not unwrapped.lstrip().startswith("{")


def test_unwrap_embedded_log_text_nested_dict_and_plain_passthrough() -> None:
    nested = {"message": json.dumps({"content": _INNER_LOG})}
    assert "HarvardManageMentorCourseImpl" in unwrap_embedded_log_text(nested)
    assert unwrap_embedded_log_text("plain boom") == "plain boom"
    assert unwrap_embedded_log_text(None) == ""


def test_unwrap_embedded_log_text_stack_trace_key() -> None:
    payload = {"stackTrace": _INNER_LOG, "level": "ERROR"}
    assert "HarvardManageMentorCourseImpl.java:169" in unwrap_embedded_log_text(payload)


def test_unwrap_embedded_log_text_salvages_truncated_json() -> None:
    truncated = (
        '{"content":"2026-09-03 21:05:01.639 third-ability-service [SOFA] ERROR\\n'
        "java.lang.NumberFormatException: bad\\n"
        "\\tat com.coolcollege.Foo.bar(Foo.java:12)\\n"
        "\\tat com.coolcollege.Baz.run(Baz.java:3"
    )
    unwrapped = unwrap_embedded_log_text(truncated)
    assert "NumberFormatException" in unwrapped
    assert "Foo.bar(Foo.java:12)" in unwrapped
    assert "third-ability-service" in unwrapped
