-- Статус и диагностика кандидатов CSG: подтверждение %w{1,n}, чужие совпадения.

ALTER TABLE candidate_groups ADD COLUMN status TEXT NOT NULL DEFAULT 'auto_validated';
ALTER TABLE candidate_groups ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE candidate_groups ADD COLUMN foreign_matches INTEGER NOT NULL DEFAULT 0;
