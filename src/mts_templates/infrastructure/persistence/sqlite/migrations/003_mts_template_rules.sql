-- Шаблоны по правилам МТС: операторы, тип трафика и пример текста.
-- Метрики: «покрытие» и подсчёт по методам матчинга заменены на срабатывания.

ALTER TABLE templates ADD COLUMN operators_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE templates ADD COLUMN traffic_type TEXT NOT NULL DEFAULT '';
ALTER TABLE templates ADD COLUMN example TEXT NOT NULL DEFAULT '';

ALTER TABLE template_metrics ADD COLUMN triggered_messages INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics RENAME COLUMN coverage TO trigger_rate;
ALTER TABLE template_metrics DROP COLUMN exact_matches;
ALTER TABLE template_metrics DROP COLUMN pattern_matches;
ALTER TABLE template_metrics DROP COLUMN fuzzy_matches;
