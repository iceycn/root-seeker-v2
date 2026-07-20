-- RootSeeker schema for MySQL 8+
-- Used by Docker entrypoint (mysql/init) and custom database bootstrap (scripts/init_mysql.py).

CREATE TABLE IF NOT EXISTS cases (
    case_id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    symptom TEXT NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    source VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    selected_skills JSON,
    steps JSON,
    metadata JSON,
    created_at VARCHAR(64),
    updated_at VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS evidence_packs (
    case_id VARCHAR(255) PRIMARY KEY,
    summary TEXT,
    items JSON,
    created_at VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS reports (
    case_id VARCHAR(255) PRIMARY KEY,
    title TEXT,
    summary TEXT,
    root_cause JSON,
    evidence_item_ids JSON,
    metadata JSON,
    generated_at VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    kind VARCHAR(64) NOT NULL,
    case_id VARCHAR(255),
    flow_id VARCHAR(255),
    skill_slug VARCHAR(255),
    status VARCHAR(64) NOT NULL,
    payload JSON,
    result_ref TEXT,
    error JSON,
    created_at VARCHAR(64),
    updated_at VARCHAR(64),
    INDEX idx_tasks_status (status),
    INDEX idx_tasks_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS checkpoints (
    flow_run_id VARCHAR(255) PRIMARY KEY,
    revision INT NOT NULL,
    payload JSON NOT NULL,
    updated_at VARCHAR(64) NOT NULL,
    INDEX idx_checkpoints_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admin_config (
    doc_id VARCHAR(64) PRIMARY KEY,
    payload JSON NOT NULL,
    updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cron_job_states (
    job_id VARCHAR(255) PRIMARY KEY,
    payload JSON NOT NULL,
    updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cron_job_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    payload JSON NOT NULL,
    finished_at VARCHAR(64) NOT NULL,
    INDEX idx_cron_runs_job (job_id),
    INDEX idx_cron_runs_finished (finished_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS error_chat_history (
    id VARCHAR(255) PRIMARY KEY,
    created_at VARCHAR(64) NOT NULL,
    payload JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Replay tables intentionally omitted: runtime replay still uses in-memory ReplayStore.
-- Add MysqlReplayStore + matching schema when/if replay persistence is required.
