"""Rule-based one-line problem summary for notify and error-chat UI."""

from __future__ import annotations

from collections.abc import Sequence

from rootseeker.analysis.call_chain import extract_call_chain_summary, extract_exception_summary
from rootseeker.analysis.service_identity import is_placeholder_service_name
from rootseeker.contracts.evidence import EvidencePack

__all__ = ["build_problem_summary", "problem_summary_from_pack"]


def build_problem_summary(
    *,
    symptom: str = "",
    service_name: str = "",
    exception: str = "",
    call_chain: Sequence[str] | None = None,
    max_chars: int = 180,
) -> str:
    """Build a deterministic human-readable problem line (no LLM)."""
    exc = str(exception or "").strip() or extract_exception_summary(symptom, max_chars=max_chars)
    exc_short = _short_exception(exc)

    fault = ""
    if call_chain:
        for item in call_chain:
            fault = _fault_method_label(str(item))
            if fault:
                break
    if not fault:
        frames = extract_call_chain_summary(symptom, max_frames=1)
        if frames:
            fault = _fault_method_label(frames[0])

    service = str(service_name or "").strip()
    if is_placeholder_service_name(service):
        service = ""

    if service and fault and exc_short:
        text = f"{service} 在 {fault} 抛出 {exc_short}"
    elif service and exc_short:
        text = f"{service} 抛出 {exc_short}"
    elif fault and exc_short:
        text = f"在 {fault} 抛出 {exc_short}"
    elif service and fault:
        text = f"{service} 在 {fault} 出现错误"
    elif exc_short:
        text = f"抛出 {exc_short}"
    elif fault:
        text = f"在 {fault} 出现错误"
    else:
        return ""

    return text[:max_chars].rstrip()


def problem_summary_from_pack(
    pack: EvidencePack,
    *,
    service_name: str = "",
    symptom: str = "",
    max_chars: int = 180,
) -> str:
    """Prefer normalize-extracted fields; fall back to raw symptom text."""
    exception = ""
    chain: list[str] = []
    resolved_service = str(service_name or "").strip()
    for item in pack.items:
        content = item.content or {}
        extracted = content.get("extracted")
        if not isinstance(extracted, dict):
            continue
        if not exception:
            value = extracted.get("exception_summary")
            if isinstance(value, str) and value.strip():
                exception = value.strip()
        if not chain:
            value = extracted.get("call_chain")
            if isinstance(value, list):
                chain = [str(x).strip() for x in value if str(x).strip()]
        if not resolved_service:
            value = extracted.get("service_name")
            if isinstance(value, str) and value.strip():
                resolved_service = value.strip()
    return build_problem_summary(
        symptom=symptom,
        service_name=resolved_service,
        exception=exception,
        call_chain=chain,
        max_chars=max_chars,
    )


def _short_exception(exception: str) -> str:
    text = str(exception or "").strip()
    if not text:
        return ""
    if ":" in text:
        left, right = text.split(":", 1)
        simple = left.rsplit(".", 1)[-1].strip()
        return f"{simple}:{right}" if right.startswith(" ") else f"{simple}: {right.lstrip()}"
    return text.rsplit(".", 1)[-1].strip()


def _fault_method_label(frame: str) -> str:
    text = str(frame or "").strip()
    if not text:
        return ""
    if " (" in text:
        text = text.split(" (", 1)[0].strip()
    return text
