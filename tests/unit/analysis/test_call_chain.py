from __future__ import annotations

import json

from rootseeker.analysis.call_chain import (
    extract_call_chain_summary,
    extract_code_path,
    extract_exception_summary,
)


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


def test_extract_exception_summary_prefers_innermost_caused_by() -> None:
    stack = """
org.springframework.jdbc.UncategorizedSQLException: Error attempting to get column 'name_encrypted' from result set.  Cause: java.sql.SQLException: AES解密失败
	at org.springframework.jdbc.support.AbstractFallbackSQLExceptionTranslator.translate(AbstractFallbackSQLExceptionTranslator.java:89)
Caused by: java.sql.SQLException: AES解密失败
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:53)
Caused by: java.lang.IllegalArgumentException: Input byte array has wrong 4-byte ending unit
	at java.util.Base64$Decoder.decode0(Base64.java:704)
	at net.coolcollege.usercenter.facade.utils.AesEncryptUtil.decrypt(AesEncryptUtil.java:61)
"""
    summary = extract_exception_summary(stack)
    assert "IllegalArgumentException" in summary
    assert "wrong 4-byte ending unit" in summary
    assert "UncategorizedSQLException" not in summary


def test_code_read_defaults_to_fault_file_not_spring_translator() -> None:
    from rootseeker.contracts.case import CaseCreateRequest
    from rootseeker.skill_runtime.rule_step_argument_resolver import RuleStepArgumentResolver

    stack = """
org.springframework.jdbc.UncategorizedSQLException: Error attempting to get column 'name_encrypted'
	at org.springframework.jdbc.support.AbstractFallbackSQLExceptionTranslator.translate(AbstractFallbackSQLExceptionTranslator.java:89)
Caused by: java.sql.SQLException: AES解密失败
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:53)
Caused by: java.lang.IllegalArgumentException: Input byte array has wrong 4-byte ending unit
	at java.util.Base64$Decoder.decode0(Base64.java:704)
	at net.coolcollege.usercenter.facade.utils.AesEncryptUtil.decrypt(AesEncryptUtil.java:61)
"""
    args = RuleStepArgumentResolver().resolve(
        "code.read",
        CaseCreateRequest(
            title="t",
            symptom=stack,
            service_name="training-manage-api",
            source="unit",
        ),
    )
    assert args["path"] == "AesEncryptUtil.java"
    assert "AbstractFallbackSQLExceptionTranslator.java" not in args["path"]


AES_STACK = """
org.springframework.jdbc.UncategorizedSQLException: Error attempting to get column 'name_encrypted' from result set.  Cause: java.sql.SQLException: AES解密失败
	at org.springframework.jdbc.support.AbstractFallbackSQLExceptionTranslator.translate(AbstractFallbackSQLExceptionTranslator.java:89)
	at net.coolcollege.training.service.impl.BizPracticeService.queryBizPracticeListByUserDepaGroupPost(BizPracticeService.java:2361)
	at net.coolcollege.training.service.impl.BizPracticeService.getPracticeList(BizPracticeService.java:1275)
	at net.coolcollege.training.controller.BizPracticeController.getPracticeList(BizPracticeController.java:88)
Caused by: java.sql.SQLException: AES解密失败
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:53)
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.getNullableResult(AesTypeHandler.java:28)
	at com.github.pagehelper.PageInterceptor.intercept(PageInterceptor.java:143)
Caused by: java.lang.IllegalArgumentException: Input byte array has wrong 4-byte ending unit
	at java.util.Base64$Decoder.decode0(Base64.java:704)
	at java.util.Base64$Decoder.decode(Base64.java:526)
	at net.coolcollege.usercenter.facade.utils.AesEncryptUtil.decrypt(AesEncryptUtil.java:61)
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:51)
"""


def test_extract_call_chain_puts_innermost_app_frames_first() -> None:
    chain = extract_call_chain_summary(AES_STACK)
    assert chain, "expected application frames"
    assert "queryBizPracticeListByUserDepaGroupPost" not in chain[0]
    assert any(name in chain[0] for name in ("AesEncryptUtil.decrypt", "AesTypeHandler.decryptField"))
    joined = "\n".join(chain)
    assert "Base64" not in joined
    assert "PageInterceptor" not in joined
    assert "AbstractFallbackSQLExceptionTranslator" not in joined


def test_extract_code_path_skips_logger_abbrev_and_spring_file() -> None:
    from mcp_servers.internal.handlers import _extract_code_path

    logger_stack = (
        "n.c.u.s.b.impl.SysUserGroupService:1336: import user group 导入用户组解析Excel文件错误:\n"
        "net.coolcollege.platform.cool.common.error.v2.ServiceException: "
        '{"err_msg_list":["无法识别文件；"]}\n'
        "\tat net.coolcollege.usercenter.service.business.impl.SysUserGroupService"
        ".parseFile(SysUserGroupService.java:1333)\n"
        "\tat net.coolcollege.usercenter.controller.v2.SysUserGroupControllerV2"
        ".parse(SysUserGroupControllerV2.java:172)\n"
    )
    assert _extract_code_path(logger_stack) == "SysUserGroupService.java"

    assert _extract_code_path(AES_STACK) == "AesEncryptUtil.java"
    assert _extract_code_path("boom in Service.java:12") == "Service.java"


_SLS_NUMBER_FORMAT_LOG = (
    "2026-09-03 21:05:01.639 third-ability-service [SOFA-SEV-BOLT-BIZ-12200-10-T20] INFO  "
    "c.c.t.s.i.HarvardManageMentorCourseImpl - harvard manage mentor getCourses error\n"
    "java.lang.NumberFormatException: For input string: \"user@example.com\"\n"
    "\tat java.lang.NumberFormatException.forInputString(NumberFormatException.java:65)\n"
    "\tat java.lang.Long.parseLong(Long.java:589)\n"
    "\tat java.lang.Long.valueOf(Long.java:803)\n"
    "\tat com.coolcollege.thirdability.service.impl.HarvardManageMentorCourseImpl"
    ".getCourseProgress(HarvardManageMentorCourseImpl.java:169)\n"
    "\tat com.coolcollege.thirdability.facade.impl.ThirdCourseFacadeImpl"
    ".getCourseProgress(ThirdCourseFacadeImpl.java:299)\n"
)


def test_extract_call_chain_skips_java_lang_frames() -> None:
    chain = extract_call_chain_summary(_SLS_NUMBER_FORMAT_LOG)
    joined = "\n".join(chain)
    assert chain[0].startswith("HarvardManageMentorCourseImpl.getCourseProgress")
    assert "ThirdCourseFacadeImpl.getCourseProgress" in joined
    assert "NumberFormatException" not in joined
    assert "Long.parseLong" not in joined
    assert "Long.valueOf" not in joined


def test_extract_code_path_skips_jdk_exception_file() -> None:
    assert extract_code_path(_SLS_NUMBER_FORMAT_LOG) == "HarvardManageMentorCourseImpl.java"


def test_extract_call_chain_unwraps_sls_content_json() -> None:
    wrapped = json.dumps({"content": _SLS_NUMBER_FORMAT_LOG})
    chain = extract_call_chain_summary(wrapped)
    assert chain
    assert chain[0].startswith("HarvardManageMentorCourseImpl.getCourseProgress")
    summary = extract_exception_summary(wrapped)
    assert "NumberFormatException" in summary
    assert extract_code_path(wrapped) == "HarvardManageMentorCourseImpl.java"
