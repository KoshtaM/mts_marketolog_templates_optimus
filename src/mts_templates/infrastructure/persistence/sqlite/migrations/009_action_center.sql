-- Центр действий: объёмы и стоимость сообщений, подпавших под шаблон,
-- но оплаченных как обычные. Нужны для оценки потерь по шаблону.

ALTER TABLE template_metrics ADD COLUMN untriggered_messages INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN untriggered_segments INTEGER NOT NULL DEFAULT 0;
ALTER TABLE template_metrics ADD COLUMN untriggered_cost_kopecks INTEGER NOT NULL DEFAULT 0;

-- Старые прогоны не содержат новых полей: сбрасываем кэш, чтобы он пересчитался.
DELETE FROM analysis_runs;
