-- Начальная схема MTS SMS Templates Optimus.
-- Деньги хранятся в копейках (INTEGER), чтобы не терять точность.
-- Даты — ISO 8601 с часовым поясом в TEXT.

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    kind TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    period_from TEXT,
    period_to TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    total_cost_kopecks INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_import_batches_sha256
    ON import_batches(source_sha256);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    sent_at TEXT NOT NULL,
    recipient TEXT NOT NULL,
    operator TEXT NOT NULL,
    sender TEXT NOT NULL,
    text TEXT NOT NULL,
    segments INTEGER NOT NULL,
    message_class TEXT NOT NULL,
    cost_kopecks INTEGER NOT NULL,
    delivered INTEGER NOT NULL,
    package_type TEXT,
    send_status TEXT,
    delivery_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_batch ON messages(batch_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_date ON messages(sender, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_operator_date ON messages(operator, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_class ON messages(message_class);

CREATE TABLE IF NOT EXISTS billing_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    package_type TEXT,
    price_per_segment_kopecks INTEGER,
    cost_kopecks INTEGER NOT NULL,
    segments INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_billing_rows_message ON billing_rows(message_id);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    sender TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    monthly_fee_kopecks INTEGER NOT NULL DEFAULT 200000,
    registered_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(batch_id, config_hash)
);

CREATE TABLE IF NOT EXISTS template_metrics (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    template_id TEXT NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    active INTEGER NOT NULL,
    matched_messages INTEGER NOT NULL,
    matched_segments INTEGER NOT NULL,
    actual_cost_kopecks INTEGER NOT NULL,
    baseline_cost_kopecks INTEGER NOT NULL,
    template_fee_kopecks INTEGER NOT NULL,
    net_benefit_kopecks INTEGER NOT NULL,
    coverage REAL NOT NULL,
    PRIMARY KEY (run_id, template_id)
);

CREATE TABLE IF NOT EXISTS candidate_groups (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    group_id TEXT NOT NULL,
    template_text TEXT NOT NULL,
    messages INTEGER NOT NULL,
    segments INTEGER NOT NULL,
    actual_cost_kopecks INTEGER NOT NULL,
    baseline_cost_kopecks INTEGER NOT NULL,
    monthly_saving_kopecks INTEGER NOT NULL,
    template_fee_kopecks INTEGER NOT NULL,
    net_monthly_kopecks INTEGER NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (run_id, group_id)
);
