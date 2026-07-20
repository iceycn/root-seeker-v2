#!/usr/bin/env bash
# Sync COMPOSE_PROFILES with ROOTSEEKER_STORAGE_BACKEND from .env (or environment).
# mysql/memory-with-mysql -> enable profile "mysql"; sqlite/memory -> disable mysql service.

_env_get() {
    local key="$1"
    if [ -n "${!key:-}" ]; then
        printf '%s' "${!key}"
        return
    fi
    if [ -f .env ]; then
        local line
        line="$(grep -E "^${key}=" .env | tail -n1 || true)"
        if [ -n "$line" ]; then
            printf '%s' "${line#*=}" | tr -d '"' | tr -d "'"
            return
        fi
    fi
    printf ''
}

sync_storage_compose_profiles() {
    local backend
    backend="$(_env_get ROOTSEEKER_STORAGE_BACKEND)"
    backend="$(printf '%s' "$backend" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    if [ -z "$backend" ]; then
        backend="mysql"
    fi

    case "$backend" in
        sqlite|memory)
            export COMPOSE_PROFILES=""
            echo "[INFO] storage=$backend -> mysql profile OFF (sqlite/memory, no mysql container)"
            ;;
        *)
            export COMPOSE_PROFILES="mysql"
            echo "[INFO] storage=$backend -> mysql profile ON"
            ;;
    esac
}
