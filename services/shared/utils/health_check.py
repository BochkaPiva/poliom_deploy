"""
Утилиты для проверки состояния сервисов (health checks)
"""
import os
import sys
from sqlalchemy import create_engine, text
from celery import Celery

# Добавляем корневую директорию проекта в PYTHONPATH,
# чтобы обеспечить корректный импорт модулей.
# Это необходимо, так как скрипт может вызываться из разных контекстов.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

def check_database():
    """
    Проверяет доступность базы данных.
    Читает URL из переменных окружения и пытается выполнить простой запрос.
    """
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("Переменная окружения DATABASE_URL не установлена.")
            return False
            
        engine = create_engine(db_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Подключение к базе данных успешно.")
        return True
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return False

def check_celery():
    """
    Проверяет доступность брокера сообщений Celery (Redis).
    Читает URL из переменных окружения и пытается установить соединение.
    """
    try:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            print("Переменная окружения REDIS_URL не установлена.")
            return False

        celery_app = Celery('tasks', broker=redis_url)
        celery_app.broker_connection().ensure_connection(max_retries=3)
        print("Подключение к брокеру Celery (Redis) успешно.")
        return True
    except Exception as e:
        print(f"Ошибка подключения к брокеру Celery (Redis): {e}")
        return False

if __name__ == '__main__':
    """
    Позволяет запускать проверки из командной строки для отладки.
    Пример: python -m shared.utils.health_check db
             python -m shared.utils.health_check celery
    """
    if len(sys.argv) > 1:
        check_type = sys.argv[1]
        if check_type == "db":
            exit(0) if check_database() else exit(1)
        elif check_type == "celery":
            exit(0) if check_celery() else exit(1)
        else:
            print(f"Неизвестный тип проверки: {check_type}")
            exit(1)
    else:
        print("Укажите тип проверки: 'db' или 'celery'")
        exit(1) 