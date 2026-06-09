from __future__ import annotations

import pytest

from rootseeker.channel_routing import set_default_channel_registry


@pytest.fixture(autouse=True)
def reset_default_channel_registry_after_test() -> None:
    yield
    set_default_channel_registry(None)
