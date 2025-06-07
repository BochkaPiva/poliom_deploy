-- Инициализация базы данных POLIOM
-- Автоматическое создание расширения pgvector

-- Создаем расширение pgvector если его нет
CREATE EXTENSION IF NOT EXISTS vector;

-- Проверяем, что расширение установлено
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'Расширение pgvector не установлено! Проверьте образ PostgreSQL.';
    END IF;
    
    RAISE NOTICE 'Расширение pgvector успешно установлено и готово к использованию.';
END $$; 