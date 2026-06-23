from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rootseeker.contracts.repository import RepositoryRef
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.skill import SkillSourceKind, SkillSpec

__all__ = ["AdminConfigStore"]


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
            return {
                "repos": [],
                "catalog": [],
                "skills": [],
                "settings": {},
                "ai_providers": [],
                "callbacks": [],
                "error_chat": [],
                "repo_remotes": [],
            }
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                "repos": [],
                "catalog": [],
                "skills": [],
                "settings": {},
                "ai_providers": [],
                "callbacks": [],
                "error_chat": [],
                "repo_remotes": [],
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
        data["repo_remotes"] = [item for item in data.get("repo_remotes", []) if item.get("name") != name]
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

    def upsert_env_var(self, key: str, value: str, *, secret: bool = False, scope: str = "runtime") -> None:
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
        data["ai_providers"] = [item for item in data.get("ai_providers", []) if item.get("name") != name]
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
