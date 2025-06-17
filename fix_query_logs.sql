-- Исправление структуры таблицы query_logs
-- Переименование колонки query_text в query для соответствия новой модели

-- Проверяем существование старой колонки и переименовываем её
DO $$
BEGIN
    -- Проверяем существует ли колонка query_text
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'query_logs' 
        AND column_name = 'query_text'
    ) THEN
        -- Переименовываем query_text в query
        ALTER TABLE query_logs RENAME COLUMN query_text TO query;
        RAISE NOTICE 'Колонка query_text переименована в query';
    ELSE
        RAISE NOTICE 'Колонка query_text не найдена или уже переименована';
    END IF;
    
    -- Проверяем существует ли колонка response_text и переименовываем её
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'query_logs' 
        AND column_name = 'response_text'
    ) THEN
        -- Переименовываем response_text в response
        ALTER TABLE query_logs RENAME COLUMN response_text TO response;
        RAISE NOTICE 'Колонка response_text переименована в response';
    ELSE
        RAISE NOTICE 'Колонка response_text не найдена или уже переименована';
    END IF;
END $$; 