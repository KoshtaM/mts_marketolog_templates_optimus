-- Сегменты логического сообщения — сумма сегментов биллинговых строк.
-- Длинная SMS оплачивается несколькими частями (например, 23 + 5 + 15),
-- ранее брался максимум, из-за чего счёт сегментов расходился с ЛК.

UPDATE messages
SET segments = (
    SELECT COALESCE(SUM(billing_rows.segments), messages.segments)
    FROM billing_rows
    WHERE billing_rows.message_id = messages.id
);

UPDATE import_batches
SET segment_count = (
    SELECT COALESCE(SUM(messages.segments), 0)
    FROM messages
    WHERE messages.batch_id = import_batches.id
);

DELETE FROM analysis_runs;
