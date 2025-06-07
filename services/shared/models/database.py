"""
Конфигурация базы данных для POLIOM HR Assistant
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок базы данных
def get_database_url():
    """Получает URL базы данных из переменных окружения"""
    return os.getenv("DATABASE_URL", "postgresql://rag_user:rag_password@localhost:5432/rag_db")

# Инициализируем движок
engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False  # Установите True для отладки SQL запросов
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 