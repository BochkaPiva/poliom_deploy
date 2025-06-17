-- Инициализация расширения pgvector для PostgreSQL
-- Простая инициализация для локального развертывания

-- Создаем расширение pgvector если его нет
CREATE EXTENSION IF NOT EXISTS vector;

-- Проверяем, что расширение установлено
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'Расширение pgvector не установлено! Проверьте образ PostgreSQL.';
    END IF;
    
    RAISE NOTICE 'Расширение pgvector установлено и готово к использованию.';
END $$; 