from __future__ import annotations

from rootseeker.contracts.log_query import LogQueryTemplate

__all__ = ["render_query_template"]


def render_query_template(template: LogQueryTemplate, parameters: dict[str, object]) -> str:
    rendered = template.template_body
    for key, value in parameters.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered
