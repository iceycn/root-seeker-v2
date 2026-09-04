from rootseeker.analysis.service_identity import (
    extract_service_name_from_text,
    is_placeholder_service_name,
    resolve_service_name,
)


def test_extract_service_name_from_logback_bracket() -> None:
    text = (
        "2026-07-14 13:49:24.473 [training-manage-api] [http-nio-30000-exec-34] [ERROR] "
        "PopRecordService.insertPopRecordLogic failed"
    )
    assert extract_service_name_from_text(text) == "training-manage-api"


def test_extract_service_name_from_kv() -> None:
    assert extract_service_name_from_text('service_name="checkout-api" boom') == "checkout-api"
    assert extract_service_name_from_text("appName: payment-service") == "payment-service"


def test_extract_ignores_thread_brackets() -> None:
    text = "oops [http-nio-30000-exec-14] NullPointerException"
    assert extract_service_name_from_text(text) is None


def test_resolve_prefers_explicit_over_text() -> None:
    text = "2026-07-14 13:49:24.473 [training-manage-api] boom"
    assert resolve_service_name("billing-api", text=text) == "billing-api"
    assert resolve_service_name("order-service", text=text) == "order-service"
    assert resolve_service_name(None, text=text) == "training-manage-api"


def test_placeholder_detection() -> None:
    assert is_placeholder_service_name("unknown-service")
    assert is_placeholder_service_name("")
    assert not is_placeholder_service_name("order-service")
    assert not is_placeholder_service_name("training-manage-api")


def test_extract_service_name_from_sofa_bare_service() -> None:
    text = (
        "2026-09-03 21:05:01.639 third-ability-service [SOFA-SEV-BOLT-BIZ-12200-10-T20] INFO  "
        "c.c.t.s.i.HarvardManageMentorCourseImpl - harvard manage mentor getCourses error"
    )
    assert extract_service_name_from_text(text) == "third-ability-service"


def test_extract_service_name_unwraps_sls_content_json() -> None:
    import json

    wrapped = json.dumps(
        {
            "content": (
                "2026-09-03 21:05:01.639 third-ability-service "
                "[SOFA-SEV-BOLT-BIZ-12200-10-T20] INFO  boom"
            )
        }
    )
    assert extract_service_name_from_text(wrapped) == "third-ability-service"
