-- Дополнительные колонки метрик, кандидатов и статистики импорта.
-- Схема 001 создавалась под минимальный набор полей; здесь добавляем всё,
-- что нужно экранам «Дашборд», «Шаблоны», «Кандидаты» и отчёту.

ALTER TABLE import_batches ADD COLUMN segment_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN duplicate_message_ids INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN delivered_rows INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN partial_delivered_rows INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN send_error_rows INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN delivery_error_rows INTEGER NOT NULL DEFAULT 0;
ALTER TABLE import_batches ADD COLUMN empty_package_rows INTEGER NOT NULL DEFAULT 0;

ALTER TABLE template_metrics ADD COLUMN delivered_messages INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN unique_recipients INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN exact_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN pattern_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN fuzzy_matches INTEGER NOT NULL DEFAULT 0;

ALTER TABLE candidate_groups ADD COLUMN payback_months REAL;
ALTER TABLE candidate_groups ADD COLUMN coverage REAL NOT NULL DEFAULT 0;
ALTER TABLE candidate_groups ADD COLUMN senders_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE candidate_groups ADD COLUMN operators_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE candidate_groups ADD COLUMN period_from TEXT;
ALTER TABLE candidate_groups ADD COLUMN period_to TEXT;
ALTER TABLE candidate_groups ADD COLUMN is_partial INTEGER NOT NULL DEFAULT 0;
ALTER TABLE candidate_groups ADD COLUMN examples_json TEXT NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_messages_batch_class ON messages(batch_id, message_class);
CREATE INDEX IF NOT EXISTS idx_messages_batch_delivered ON messages(batch_id, delivered);
