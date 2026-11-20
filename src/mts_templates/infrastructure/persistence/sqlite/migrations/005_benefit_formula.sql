-- Методика выгоды кандидата: вместо «baseline» храним оценку стоимости по
-- тарифу шаблонированных SMS (средняя стоимость сегмента × сегменты группы).

ALTER TABLE candidate_groups DROP COLUMN baseline_cost_kopecks;
ALTER TABLE candidate_groups ADD COLUMN templated_cost_kopecks INTEGER NOT NULL DEFAULT 0;
