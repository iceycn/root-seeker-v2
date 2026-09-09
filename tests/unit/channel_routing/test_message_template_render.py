"""Tests for minimal notify message template renderer."""

from __future__ import annotations

from rootseeker.channel_routing.message_template_render import render_message_template


def test_replaces_variables() -> None:
    assert render_message_template("Hi {{name}}", {"name": "Ada"}) == "Hi Ada"


def test_conditional_block_omits_when_empty() -> None:
    body = "A\n{{#service}}服务：{{service}}\n{{/service}}B"
    assert render_message_template(body, {"service": ""}) == "A\nB"
    assert render_message_template(body, {"service": "api"}) == "A\n服务：api\nB"


def test_unknown_variable_becomes_empty() -> None:
    assert render_message_template("x{{missing}}y", {}) == "xy"
