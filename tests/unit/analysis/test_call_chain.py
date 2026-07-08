from __future__ import annotations

from rootseeker.analysis.call_chain import extract_call_chain_summary, extract_exception_summary


SAMPLE_STACK = """
org.springframework.dao.DuplicateKeyException:
### Error updating database.
at net.coolcollege.training.service.impl.PopRecordService.insertPopRecordLogic(PopRecordService.java:60)
at net.coolcollege.training.service.impl.StudyProjectProcessService.batchDealProjectQualifiedEvent(StudyProjectProcessService.java:1753)
at net.coolcollege.training.service.complete.ProjectQualifiedEventHandler.onEvent(ProjectQualifiedEventHandler.java:121)
at net.coolcollege.training.service.impl.StudyProjectService.saveProjectProgress(StudyProjectService.java:11833)
at net.coolcollege.training.controller.StudyProjectController.saveProgress(StudyProjectController.java:1132)
at org.springframework.web.servlet.FrameworkServlet.doPost(FrameworkServlet.java:901)
at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:231)
"""


def test_extract_call_chain_summary_filters_framework_frames() -> None:
    chain = extract_call_chain_summary(SAMPLE_STACK)
    assert chain == [
        "PopRecordService.insertPopRecordLogic (PopRecordService.java:60)",
        "StudyProjectProcessService.batchDealProjectQualifiedEvent (StudyProjectProcessService.java:1753)",
        "ProjectQualifiedEventHandler.onEvent (ProjectQualifiedEventHandler.java:121)",
        "StudyProjectService.saveProjectProgress (StudyProjectService.java:11833)",
        "StudyProjectController.saveProgress (StudyProjectController.java:1132)",
    ]


def test_extract_exception_summary() -> None:
    summary = extract_exception_summary(SAMPLE_STACK)
    assert "DuplicateKeyException" in summary
