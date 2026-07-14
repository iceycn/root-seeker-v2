from rootseeker.code_index.gitnexus_cli import _rewrite_path_for_sidecar


def test_rewrite_path_for_sidecar_windows_style() -> None:
    mapped = _rewrite_path_for_sidecar(
        r"E:\CodeProjects\root-seeker-v2\repos\demo",
        r"E:\CodeProjects\root-seeker-v2\repos:/data/repos",
    )
    assert mapped.replace("\\", "/") == "/data/repos/demo"


def test_rewrite_path_for_sidecar_noop_without_map() -> None:
    assert _rewrite_path_for_sidecar("/data/repos/demo", None) == "/data/repos/demo"
