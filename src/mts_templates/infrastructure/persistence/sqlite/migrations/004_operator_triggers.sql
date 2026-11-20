-- Срабатывание считается от сообщений, подпавших под шаблон; добавлен счётчик
-- сообщений, у которых оператор не входит в список шаблона.

ALTER TABLE template_metrics ADD COLUMN off_operator_messages INTEGER NOT NULL DEFAULT 0;
