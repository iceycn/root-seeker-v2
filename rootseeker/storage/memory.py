from __future__ import annotations

from rootseeker.contracts.case import CaseRecord
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack
from rootseeker.contracts.report import CaseReport

__all__ = ["InMemoryCaseStore", "InMemoryEvidenceStore", "InMemoryReportStore"]


class InMemoryCaseStore:
    def __init__(self) -> None:
        self._by_id: dict[str, CaseRecord] = {}

    def put(self, case: CaseRecord) -> None:
        self._by_id[case.case_id] = case

    def get(self, case_id: str) -> CaseRecord | None:
        return self._by_id.get(case_id)

    def list_all(self) -> list[CaseRecord]:
        return list(self._by_id.values())


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._packs: dict[str, EvidencePack] = {}

    def put_pack(self, pack: EvidencePack) -> None:
        self._packs[pack.case_id] = pack

    def get_pack(self, case_id: str) -> EvidencePack | None:
        return self._packs.get(case_id)

    def append_items(self, case_id: str, items: list[EvidenceItem]) -> EvidencePack:
        existing = self._packs.get(case_id)
        if existing is None:
            pack = EvidencePack(case_id=case_id, items=list(items), summary="")
            self._packs[case_id] = pack
            return pack
        merged = EvidencePack(
            case_id=case_id,
            items=[*existing.items, *items],
            summary=existing.summary,
        )
        self._packs[case_id] = merged
        return merged


class InMemoryReportStore:
    def __init__(self) -> None:
        self._by_case_id: dict[str, CaseReport] = {}

    def put(self, report: CaseReport) -> None:
        self._by_case_id[report.case_id] = report

    def get(self, case_id: str) -> CaseReport | None:
        return self._by_case_id.get(case_id)
