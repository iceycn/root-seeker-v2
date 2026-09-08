from __future__ import annotations

from rootseeker.analysis.problem_summary import build_problem_summary


_STACK = (
    "2026-09-08 11:24:52.776 [knowledge-api-service] ERROR boom\n"
    "net.coolcollege.platform.cool.common.error.exception.BusinessException: rpc interface error!\n"
    "\tat com.coolcollege.knowledge.service.mq.consumer.CourseWorkflowMessageListener"
    ".sendCourseApprovalOAMessage(CourseWorkflowMessageListener.java:266)\n"
    "\tat com.coolcollege.knowledge.service.mq.consumer.CourseWorkflowMessageListener"
    ".courseWorkflowMessageListener(CourseWorkflowMessageListener.java:181)\n"
)


def test_build_problem_summary_full() -> None:
    text = build_problem_summary(
        symptom=_STACK,
        service_name="knowledge-api-service",
    )
    assert text.startswith("knowledge-api-service 在 ")
    assert "CourseWorkflowMessageListener.sendCourseApprovalOAMessage" in text
    assert "BusinessException: rpc interface error!" in text
    assert "net.coolcollege.platform" not in text
    assert ".java:266" not in text


def test_build_problem_summary_without_service() -> None:
    text = build_problem_summary(symptom=_STACK, service_name="")
    assert text.startswith("在 CourseWorkflowMessageListener.sendCourseApprovalOAMessage 抛出 ")
    assert "BusinessException" in text


def test_build_problem_summary_exception_only() -> None:
    text = build_problem_summary(
        symptom="java.lang.IllegalStateException: boom\n",
        service_name="demo-api",
    )
    assert text == "demo-api 抛出 IllegalStateException: boom"


def test_build_problem_summary_fault_only() -> None:
    text = build_problem_summary(
        symptom=(
            "something went wrong\n"
            "\tat com.example.NotifySmoke.run(NotifySmoke.java:12)\n"
        ),
        service_name="",
    )
    assert text == "在 NotifySmoke.run 出现错误"


def test_build_problem_summary_skips_placeholder_service() -> None:
    text = build_problem_summary(
        symptom="java.lang.NullPointerException: x\n",
        service_name="unknown-service",
    )
    assert "unknown-service" not in text
    assert text.startswith("抛出 NullPointerException")


def test_build_problem_summary_empty() -> None:
    assert build_problem_summary(symptom="") == ""
    assert build_problem_summary(symptom="plain text without stack") == ""


def test_build_problem_summary_uses_explicit_exception_and_chain() -> None:
    text = build_problem_summary(
        symptom="",
        service_name="svc-a",
        exception="com.foo.BarException: nope",
        call_chain=["FooService.doWork (FooService.java:9)"],
    )
    assert text == "svc-a 在 FooService.doWork 抛出 BarException: nope"
