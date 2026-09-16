"""Minimal Mustache-like renderer for notify message templates.

``{{name}}`` replaces with the variable value (missing/empty → blank).

``{{#name}}...{{/name}}`` is one pair, not two independent prefixes:
``#name`` opens a block, ``/name`` closes it. If ``name`` is empty the
whole inner text (including newlines) is dropped; otherwise the inner
text is kept and variables inside it are substituted. A lone ``#`` or
``/`` tag does nothing.
"""

from __future__ import annotations

import re

__all__ = ["render_message_template"]

_COND = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
_VAR = re.compile(r"\{\{(\w+)\}\}")


def render_message_template(body: str, context: dict[str, str]) -> str:
    def repl_cond(match: re.Match[str]) -> str:
        key = match.group(1)
        inner = match.group(2)
        value = str(context.get(key, "") or "")
        if not value.strip():
            return ""
        return render_message_template(inner, context)

    text = _COND.sub(repl_cond, body)

    def repl_var(match: re.Match[str]) -> str:
        return str(context.get(match.group(1), "") or "")

    return _VAR.sub(repl_var, text)
