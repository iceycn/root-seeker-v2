from scripts.setup_wizard import main, parse_args


def test_parse_path_and_storage() -> None:
    args = parse_args(["--yes", "--path", "native", "--storage", "sqlite"])
    assert args.yes is True
    assert args.path == "native"
    assert args.storage == "sqlite"


def test_yes_without_path_fails() -> None:
    code = main(["--yes", "--storage", "sqlite"])
    assert code != 0
