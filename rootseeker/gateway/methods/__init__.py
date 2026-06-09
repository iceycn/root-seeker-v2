"""Gateway business methods."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.gateway.methods.approval_methods import register_approval_methods
from rootseeker.gateway.methods.case_methods import register_case_methods
from rootseeker.gateway.methods.flow_methods import register_flow_methods
from rootseeker.gateway.methods.skill_methods import register_skill_methods
from rootseeker.gateway.methods.tool_methods import register_tool_methods

__all__ = [
    "register_all_business_methods",
    "register_approval_methods",
    "register_case_methods",
    "register_flow_methods",
    "register_skill_methods",
    "register_tool_methods",
]


def register_all_business_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register all business methods to a gateway method registry."""
    register_approval_methods(registry, runtime)
    register_case_methods(registry, runtime)
    register_flow_methods(registry, runtime)
    register_skill_methods(registry, runtime)
    register_tool_methods(registry, runtime)
