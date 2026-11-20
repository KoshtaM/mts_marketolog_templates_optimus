-- Индекс под агрегаты по абонентам: группировка по получателю внутри загрузки.
CREATE INDEX IF NOT EXISTS idx_messages_batch_recipient ON messages(batch_id, recipient);
