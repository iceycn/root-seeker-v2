from __future__ import annotations

from rootseeker.analysis.code_slice import chain_methods_for_path, slice_source_window


PARSE_FILE_SOURCE = """
package demo;

public class SysUserGroupService {
    public void other() {
        return;
    }
""" + "\n".join(f"    int pad{i} = {i};" for i in range(90)) + """

    public BaseOut parseFile(MultipartFile file, String type) {
        if (file == None) {
            throw new ServiceException("传输失败");
        }
        if (!suffix.equals(".xlsx")) {
            throw new ServiceException("文件格式错误");
        }
        List<UserGroupDto> userGroupDtos = load();
        if (userGroupDtos != null && !userGroupDtos.isEmpty()) {
            checkData();
            throw new ServiceException("550001");
        } else {
            errorMsgs.add("无法识别文件");
            throw new ServiceException("enterpriseapi.550008");
        }
    }
}
"""

AES_HANDLER_SOURCE = """
package net.coolcollege.usercenter.facade.handler;

public class AesTypeHandler extends BaseTypeHandler<String> {
    public String getNullableResult(ResultSet rs, String columnName) {
        return decryptField(rs.getString(columnName));
    }

    public String unusedHelper() {
        return "nope";
    }

    private String decryptField(String encrypted) {
        return AesEncryptUtil.decrypt(encrypted);
    }
}
"""


def test_slice_source_window_returns_enclosing_method_not_whole_file() -> None:
    lines = PARSE_FILE_SOURCE.splitlines()
    focus = next(i + 1 for i, line in enumerate(lines) if "550008" in line)
    content, start, end = slice_source_window(
        PARSE_FILE_SOURCE, focus_line=focus, methods=["parseFile"]
    )
    assert "parseFile" in content
    assert "550008" in content
    assert "无法识别文件" in content
    assert "public void other()" not in content
    assert end - start + 1 < len(lines)


def test_slice_source_window_keeps_only_call_chain_methods() -> None:
    content, _, _ = slice_source_window(
        AES_HANDLER_SOURCE,
        methods=["getNullableResult", "decryptField"],
        focus_line=5,
    )
    assert "getNullableResult" in content
    assert "decryptField" in content
    assert "AesEncryptUtil.decrypt" in content
    assert "unusedHelper" not in content


def test_slice_source_window_keeps_only_named_method_in_small_file() -> None:
    src = (
        "package p;\n"
        "public class AesTypeHandler {\n"
        "  void decryptField() { decode(); }\n"
        "  void other() { leftover(); }\n"
        "}\n"
    )
    content, _, _ = slice_source_window(src, methods=["decryptField"], focus_line=3)
    assert "decryptField" in content
    assert "decode()" in content
    assert "other" not in content
    assert "leftover" not in content


def test_chain_methods_for_path_keeps_file_local_frames() -> None:
    methods = chain_methods_for_path(
        "AesTypeHandler.java",
        [
            "AesEncryptUtil.decrypt (AesEncryptUtil.java:61)",
            "AesTypeHandler.decryptField (AesTypeHandler.java:51)",
            "AesTypeHandler.getNullableResult (AesTypeHandler.java:28)",
            "BizPracticeService.getPracticeList (BizPracticeService.java:1275)",
        ],
    )
    assert [item["name"] for item in methods] == ["decryptField", "getNullableResult"]


def test_slice_source_window_caps_huge_files_without_focus() -> None:
    src = "\n".join(f"line{i}" for i in range(1, 801))
    content, start, end = slice_source_window(src, max_lines=400)
    assert start == 1
    assert end == 400
    assert content.splitlines()[0] == "line1"
    assert len(content.splitlines()) == 400
