def test_execute_skill_flow_removed() -> None:
    import rootseeker.skill_runtime as sr
    assert not hasattr(sr, "execute_skill_flow")
