from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rootseeker.contracts.repository import RepositoryRef
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.skill import SkillSourceKind, SkillSpec

__all__ = [
    "ALLOWED_CRON_HANDLERS",
    "AdminConfigStore",
    "BUILTIN_CRON_JOBS",
    "DEFAULT_FLOW_REPLAY_JOB_ID",
    "REPO_SYNC_CHANGED_JOB_ID",
]

REPO_SYNC_CHANGED_JOB_ID = "cron.repo-sync-changed"
DEFAULT_FLOW_REPLAY_JOB_ID = "cron.default-flow-replay"

ALLOWED_CRON_HANDLERS = frozenset(
    {
        "repo.sync_changed",
        "repo.sync_all",
        "replay.default_flow",
    }
)

BUILTIN_CRON_JOBS: list[dict[str, Any]] = [
    {
        "job_id": REPO_SYNC_CHANGED_JOB_ID,
        "name": "仓库增量同步",
        "handler": "repo.sync_changed",
        "schedule": "@hourly",
        "timezone": "UTC",
        "enabled": True,
        "builtin": True,
        "deletable": False,
        "notes": "默认每小时执行：仅同步有变更的仓库，并对变更仓强制重建 GitNexus 知识图谱。",
        "metadata": {},
    },
    {
        "job_id": DEFAULT_FLOW_REPLAY_JOB_ID,
        "name": "默认 Flow 回放评估",
        "handler": "replay.default_flow",
        "schedule": "@hourly",
        "timezone": "UTC",
        "enabled": False,
        "builtin": True,
        "deletable": False,
        "notes": "默认 Flow 回放评估任务（默认关闭）。",
        "metadata": {"suite_name": "cron-default-flow", "repeat_each": 1},
    },
]


def _normalize_cron_job(raw: dict[str, Any], *, require_handler: bool = True) -> dict[str, Any]:
    job_id = str(raw.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    handler = str(raw.get("handler") or "").strip()
    if require_handler and not handler:
        raise ValueError("handler is required")
    if handler and handler not in ALLOWED_CRON_HANDLERS:
        raise ValueError(f"unsupported cron handler: {handler}")
    schedule = str(raw.get("schedule") or "").strip()
    if not schedule:
        raise ValueError("schedule is required")
    name = str(raw.get("name") or job_id).strip() or job_id
    timezone = str(raw.get("timezone") or "UTC").strip() or "UTC"
    notes = str(raw.get("notes") or "").strip()
    metadata = raw.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    return {
        "job_id": job_id,
        "name": name,
        "handler": handler,
        "schedule": schedule,
        "timezone": timezone,
        "enabled": bool(raw.get("enabled", True)),
        "builtin": bool(raw.get("builtin", False)),
        "deletable": bool(raw.get("deletable", not bool(raw.get("builtin", False)))),
        "notes": notes,
        "metadata": dict(metadata),
    }


def _seed_builtin_cron_jobs(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    by_id = {str(item.get("job_id")): dict(item) for item in jobs if isinstance(item, dict)}
    changed = False
    for builtin in BUILTIN_CRON_JOBS:
        job_id = builtin["job_id"]
        existing = by_id.get(job_id)
        if existing is None:
            by_id[job_id] = dict(builtin)
            changed = True
            continue
        # Keep user edits for schedule/enabled/name/timezone; lock identity fields.
        merged = dict(existing)
        for key in ("handler", "builtin", "deletable"):
            if merged.get(key) != builtin[key]:
                merged[key] = builtin[key]
                changed = True
        if "enabled" not in merged:
            merged["enabled"] = builtin["enabled"]
            changed = True
        if not str(merged.get("schedule") or "").strip():
            merged["schedule"] = builtin["schedule"]
            changed = True
        if not str(merged.get("name") or "").strip():
            merged["name"] = builtin["name"]
            changed = True
        if not str(merged.get("timezone") or "").strip():
            merged["timezone"] = builtin["timezone"]
            changed = True
        # One-time migrate: fill builtin default notes when field was never persisted.
        if "notes" not in existing and builtin.get("notes"):
            merged["notes"] = builtin["notes"]
            changed = True
        by_id[job_id] = merged
    # Preserve insertion order: builtins first, then custom.
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for builtin in BUILTIN_CRON_JOBS:
        job_id = builtin["job_id"]
        ordered.append(by_id[job_id])
        seen.add(job_id)
    for job_id, item in by_id.items():
        if job_id in seen:
            continue
        ordered.append(item)
    return ordered, changed


class AdminConfigStore:
    """Small JSON-backed admin configuration store.

    It intentionally stays simple: admin changes are persisted as structured JSON and replayed into
    the in-memory runtime during admin app startup.
    """

    def __init__(self, path: Path | str = "data/admin/config.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = {
                "repos": [],
                "catalog": [],
                "skills": [],
                "settings": {},
                "ai_providers": [],
                "callbacks": [],
                "error_chat": [],
                "repo_remotes": [],
                "cron_jobs": [],
            }
            cron_jobs, _ = _seed_builtin_cron_jobs([])
            data["cron_jobs"] = cron_jobs
            self.save(data)
            return data
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {
                "repos": [],
                "catalog": [],
                "skills": [],
                "settings": {},
                "ai_providers": [],
                "callbacks": [],
                "error_chat": [],
                "repo_remotes": [],
                "cron_jobs": [],
            }
        data.setdefault("repos", [])
        data.setdefault("catalog", [])
        data.setdefault("skills", [])
        data.setdefault("settings", {})
        data.setdefault("env_vars", [])
        data.setdefault("ai_providers", [])
        data.setdefault("callbacks", [])
        data.setdefault("error_chat", [])
        data.setdefault("repo_remotes", [])
        data.setdefault("cron_jobs", [])
        cron_jobs, changed = _seed_builtin_cron_jobs(
            [item for item in data.get("cron_jobs", []) if isinstance(item, dict)]
        )
        data["cron_jobs"] = cron_jobs
        if changed:
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_repos(self) -> list[RepositoryRef]:
        return [RepositoryRef.model_validate(item) for item in self.load().get("repos", [])]

    def upsert_repo(self, repo: RepositoryRef) -> None:
        data = self.load()
        repos = [item for item in data.get("repos", []) if item.get("name") != repo.name]
        repos.append(repo.model_dump(mode="json"))
        data["repos"] = repos
        self.save(data)

    def delete_repo(self, name: str) -> None:
        data = self.load()
        data["repos"] = [item for item in data.get("repos", []) if item.get("name") != name]
        self.save(data)

    def list_repo_remotes(self) -> list[dict[str, Any]]:
        return list(self.load().get("repo_remotes", []))

    def upsert_repo_remote(self, remote: dict[str, Any]) -> dict[str, Any]:
        name = str(remote.get("name", "")).strip()
        if not name:
            raise ValueError("remote name is required")
        data = self.load()
        items = [item for item in data.get("repo_remotes", []) if item.get("name") != name]
        payload = dict(remote)
        payload["name"] = name
        items.append(payload)
        data["repo_remotes"] = items
        self.save(data)
        return payload

    def delete_repo_remote(self, name: str) -> None:
        data = self.load()
        data["repo_remotes"] = [
            item for item in data.get("repo_remotes", []) if item.get("name") != name
        ]
        self.save(data)

    def list_catalog(self) -> list[ServiceCatalogEntry]:
        return [ServiceCatalogEntry.model_validate(item) for item in self.load().get("catalog", [])]

    def upsert_catalog(self, entry: ServiceCatalogEntry) -> None:
        data = self.load()
        catalog = [
            item
            for item in data.get("catalog", [])
            if not (
                item.get("tenant") == entry.tenant
                and item.get("environment") == entry.environment
                and item.get("service_name") == entry.service_name
            )
        ]
        catalog.append(entry.model_dump(mode="json"))
        data["catalog"] = catalog
        self.save(data)

    def delete_catalog(self, tenant: str, environment: str, service_name: str) -> None:
        data = self.load()
        data["catalog"] = [
            item
            for item in data.get("catalog", [])
            if not (
                item.get("tenant") == tenant
                and item.get("environment") == environment
                and item.get("service_name") == service_name
            )
        ]
        self.save(data)

    def list_skills(self) -> list[SkillSpec]:
        return [SkillSpec.model_validate(item) for item in self.load().get("skills", [])]

    def upsert_skill(self, skill: SkillSpec) -> None:
        data = self.load()
        payload = skill.model_dump(mode="json")
        payload["source_kind"] = SkillSourceKind.CUSTOM.value
        skills = [item for item in data.get("skills", []) if item.get("slug") != skill.slug]
        skills.append(payload)
        data["skills"] = skills
        self.save(data)

    def delete_skill(self, slug: str) -> None:
        data = self.load()
        data["skills"] = [item for item in data.get("skills", []) if item.get("slug") != slug]
        self.save(data)

    def get_settings(self) -> dict[str, Any]:
        return dict(self.load().get("settings", {}))

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        merged = dict(data.get("settings", {}))
        merged.update(settings)
        data["settings"] = merged
        self.save(data)
        return merged

    def list_env_vars(self) -> list[dict[str, Any]]:
        return list(self.load().get("env_vars", []))

    def upsert_env_var(
        self, key: str, value: str, *, secret: bool = False, scope: str = "runtime"
    ) -> None:
        if not key:
            raise ValueError("env key is required")
        data = self.load()
        items = [item for item in data.get("env_vars", []) if item.get("key") != key]
        items.append({"key": key, "value": value, "secret": secret, "scope": scope})
        data["env_vars"] = items
        settings = dict(data.get("settings", {}))
        settings[key] = value
        data["settings"] = settings
        self.save(data)

    def delete_env_var(self, key: str) -> None:
        data = self.load()
        data["env_vars"] = [item for item in data.get("env_vars", []) if item.get("key") != key]
        settings = dict(data.get("settings", {}))
        settings.pop(key, None)
        data["settings"] = settings
        self.save(data)

    def list_ai_providers(self) -> list[dict[str, Any]]:
        return list(self.load().get("ai_providers", []))

    def upsert_ai_provider(self, provider: dict[str, Any]) -> None:
        name = str(provider.get("name", "")).strip()
        if not name:
            raise ValueError("AI provider name is required")
        data = self.load()
        items = [item for item in data.get("ai_providers", []) if item.get("name") != name]
        items.append(dict(provider))
        data["ai_providers"] = items
        self.save(data)

    def delete_ai_provider(self, name: str) -> None:
        data = self.load()
        data["ai_providers"] = [
            item for item in data.get("ai_providers", []) if item.get("name") != name
        ]
        settings = dict(data.get("settings", {}))
        if settings.get("ROOTSEEKER_DEFAULT_AI_PROVIDER") == name:
            settings.pop("ROOTSEEKER_DEFAULT_AI_PROVIDER", None)
        data["settings"] = settings
        self.save(data)

    def set_default_ai_provider(self, name: str) -> dict[str, Any]:
        data = self.load()
        settings = dict(data.get("settings", {}))
        settings["ROOTSEEKER_DEFAULT_AI_PROVIDER"] = name
        data["settings"] = settings
        self.save(data)
        return settings

    def set_default_ai_model(self, provider: str, model: str) -> dict[str, Any]:
        data = self.load()
        settings = dict(data.get("settings", {}))
        settings["ROOTSEEKER_DEFAULT_AI_PROVIDER"] = provider
        settings["ROOTSEEKER_DEFAULT_AI_MODEL"] = model
        data["settings"] = settings
        self.save(data)
        return settings

    def list_callbacks(self) -> list[dict[str, Any]]:
        return list(self.load().get("callbacks", []))

    def upsert_callback(self, callback: dict[str, Any]) -> None:
        name = str(callback.get("name", "")).strip()
        if not name:
            raise ValueError("callback name is required")
        data = self.load()
        items = [item for item in data.get("callbacks", []) if item.get("name") != name]
        items.append(dict(callback))
        data["callbacks"] = items
        self.save(data)

    def delete_callback(self, name: str) -> None:
        data = self.load()
        data["callbacks"] = [item for item in data.get("callbacks", []) if item.get("name") != name]
        self.save(data)

    def list_error_chat(self) -> list[dict[str, Any]]:
        return list(self.load().get("error_chat", []))

    def add_error_chat_message(self, content: str) -> dict[str, Any]:
        data = self.load()
        item = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": content,
            "created_at": datetime.now(UTC).isoformat(),
        }
        data.setdefault("error_chat", []).append(item)
        self.save(data)
        return item

    def clear_error_chat(self) -> None:
        data = self.load()
        data["error_chat"] = []
        self.save(data)

    def list_cron_jobs(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.load().get("cron_jobs", []) if isinstance(item, dict)]

    def get_cron_job(self, job_id: str) -> dict[str, Any] | None:
        for item in self.list_cron_jobs():
            if item.get("job_id") == job_id:
                return dict(item)
        return None

    def upsert_cron_job(self, job: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        jobs = [item for item in data.get("cron_jobs", []) if isinstance(item, dict)]
        incoming = dict(job)
        job_id = str(incoming.get("job_id") or "").strip()
        existing = next((item for item in jobs if item.get("job_id") == job_id), None)

        if existing and existing.get("builtin"):
            # Builtin jobs: only name/schedule/timezone/enabled/notes are editable.
            payload = dict(existing)
            if "name" in incoming:
                payload["name"] = (
                    str(incoming.get("name") or payload.get("name") or job_id).strip() or job_id
                )
            if "schedule" in incoming:
                payload["schedule"] = str(incoming.get("schedule") or "").strip()
            if "timezone" in incoming:
                payload["timezone"] = str(incoming.get("timezone") or "UTC").strip() or "UTC"
            if "enabled" in incoming:
                payload["enabled"] = bool(incoming.get("enabled"))
            if "notes" in incoming:
                payload["notes"] = str(incoming.get("notes") or "").strip()
            if "metadata" in incoming and isinstance(incoming.get("metadata"), dict):
                payload["metadata"] = dict(incoming["metadata"])
            normalized = _normalize_cron_job(payload)
            normalized["builtin"] = True
            normalized["deletable"] = False
            normalized["handler"] = str(existing.get("handler") or normalized["handler"])
        else:
            if existing is None and not job_id:
                job_id = f"cron.{uuid.uuid4().hex[:12]}"
                incoming["job_id"] = job_id
            if existing is None:
                incoming.setdefault("builtin", False)
                incoming.setdefault("deletable", True)
            else:
                incoming.setdefault("builtin", bool(existing.get("builtin", False)))
                incoming.setdefault("deletable", bool(existing.get("deletable", True)))
                incoming.setdefault("handler", existing.get("handler"))
                incoming.setdefault("schedule", existing.get("schedule"))
                incoming.setdefault("name", existing.get("name"))
                incoming.setdefault("timezone", existing.get("timezone"))
                incoming.setdefault("enabled", existing.get("enabled", True))
                incoming.setdefault("notes", existing.get("notes") or "")
                incoming.setdefault("metadata", existing.get("metadata") or {})
            normalized = _normalize_cron_job(incoming)
            if normalized["builtin"]:
                raise ValueError("cannot create a builtin cron job via API")

        jobs = [item for item in jobs if item.get("job_id") != normalized["job_id"]]
        jobs.append(normalized)
        seeded, _ = _seed_builtin_cron_jobs(jobs)
        data["cron_jobs"] = seeded
        self.save(data)
        return normalized

    def delete_cron_job(self, job_id: str) -> None:
        data = self.load()
        jobs = [item for item in data.get("cron_jobs", []) if isinstance(item, dict)]
        target = next((item for item in jobs if item.get("job_id") == job_id), None)
        if target is None:
            raise KeyError(f"cron job not found: {job_id}")
        if target.get("builtin") or target.get("deletable") is False:
            raise ValueError(f"builtin cron job cannot be deleted: {job_id}")
        data["cron_jobs"] = [item for item in jobs if item.get("job_id") != job_id]
        seeded, _ = _seed_builtin_cron_jobs(data["cron_jobs"])
        data["cron_jobs"] = seeded
        self.save(data)
