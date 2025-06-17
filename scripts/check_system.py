#!/usr/bin/env python3
"""
Скрипт проверки готовности системы POLIOM
Проверяет все критически важные компоненты перед запуском
"""

import os
import sys
import time
import psycopg2
import redis
import requests
from pathlib import Path

def check_postgres_pgvector():
    """Проверка PostgreSQL и расширения pgvector"""
    try:
        # Подключение к базе данных
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:poliom_secure_2024_db_pass@localhost:5432/poliom_local')
        
        # Парсим URL
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],  # убираем первый слеш
            user=parsed.username,
            password=parsed.password
        )
        
        cursor = conn.cursor()
        
        # Проверяем подключение
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ PostgreSQL подключен: {version}")
        
        # Проверяем расширение pgvector
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        has_vector = cursor.fetchone()[0]
        
        if has_vector:
            print("✅ Расширение pgvector установлено")
            
            # Проверяем возможность создания векторных столбцов
            cursor.execute("SELECT vector_dims(ARRAY[1,2,3]::vector);")
            dims = cursor.fetchone()[0]
            print(f"✅ pgvector функционирует корректно (тест: {dims} измерений)")
        else:
            print("❌ Расширение pgvector НЕ установлено!")
            return False
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка PostgreSQL: {e}")
        return False

def check_redis():
    """Проверка Redis"""
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        r = redis.from_url(redis_url)
        
        # Проверяем подключение
        r.ping()
        print("✅ Redis подключен")
        
        # Проверяем запись/чтение
        r.set('test_key', 'test_value', ex=10)
        value = r.get('test_key')
        if value == b'test_value':
            print("✅ Redis функционирует корректно")
            r.delete('test_key')
        else:
            print("❌ Redis не может записывать/читать данные")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Redis: {e}")
        return False

def check_admin_panel():
    """Проверка админ-панели"""
    try:
        admin_url = os.getenv('ADMIN_PANEL_URL', 'http://localhost:8001')
        
        response = requests.get(f"{admin_url}/health", timeout=10)
        if response.status_code == 200:
            print("✅ Админ-панель доступна")
            return True
        else:
            print(f"❌ Админ-панель недоступна (код: {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка админ-панели: {e}")
        return False

def check_file_permissions():
    """Проверка прав доступа к файлам"""
    try:
        # Проверяем папку uploads
        uploads_dir = Path("uploads")
        uploads_dir.mkdir(exist_ok=True)
        
        # Проверяем возможность записи
        test_file = uploads_dir / "test_write.txt"
        test_file.write_text("test")
        test_file.unlink()
        
        print("✅ Права доступа к файлам корректны")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка прав доступа: {e}")
        return False

def main():
    """Основная функция проверки"""
    print("🔍 Проверка готовности системы POLIOM...")
    print("=" * 50)
    
    checks = [
        ("PostgreSQL и pgvector", check_postgres_pgvector),
        ("Redis", check_redis),
        ("Права доступа к файлам", check_file_permissions),
        ("Админ-панель", check_admin_panel),
    ]
    
    failed_checks = []
    
    for name, check_func in checks:
        print(f"\n🔍 Проверка: {name}")
        if not check_func():
            failed_checks.append(name)
    
    print("\n" + "=" * 50)
    
    if failed_checks:
        print("❌ СИСТЕМА НЕ ГОТОВА К РАБОТЕ!")
        print("Неудачные проверки:")
        for check in failed_checks:
            print(f"  - {check}")
        sys.exit(1)
    else:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! Система готова к работе.")
        sys.exit(0)

if __name__ == "__main__":
    main() 