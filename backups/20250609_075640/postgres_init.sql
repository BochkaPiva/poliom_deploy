-- Инициализация базы данных POLIOM
-- Автоматическое создание расширения pgvector

-- Создаем расширение pgvector если его нет
CREATE EXTENSION IF NOT EXISTS vector;

-- Создаем базу данных poliom если её нет (используем настройки из .env)
SELECT 'CREATE DATABASE poliom OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'poliom')\gexec

-- Даем права пользователю postgres
GRANT ALL PRIVILEGES ON DATABASE poliom TO postgres;

-- Подключаемся к базе poliom и создаем расширение там тоже
\c poliom;
CREATE EXTENSION IF NOT EXISTS vector;

-- Проверяем, что расширение установлено
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'Расширение pgvector не установлено! Проверьте образ PostgreSQL.';
    END IF;
    
    RAISE NOTICE 'Расширение pgvector успешно установлено и готово к использованию.';
END $$; 