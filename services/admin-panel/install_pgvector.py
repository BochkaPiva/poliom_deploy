#!/usr/bin/env python3
"""
Установка и настройка pgvector для оптимизации векторного поиска
"""

import sys
import os
from pathlib import Path

# Добавляем путь к services
services_path = Path(__file__).parent.parent
sys.path.append(str(services_path))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv('.env.local')

from sqlalchemy import text
from shared.models.database import SessionLocal

def install_pgvector():
    """Устанавливаем расширение pgvector"""
    print("🔧 Установка pgvector...")
    
    db = SessionLocal()
    try:
        # Устанавливаем расширение
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.commit()
        print("✅ pgvector успешно установлен")
        
        # Проверяем установку
        result = db.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'")).fetchall()
        if result:
            print(f"✅ Подтверждение: pgvector версия {result[0][1]} активен")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка установки pgvector: {e}")
        print("💡 Возможные причины:")
        print("   • pgvector не установлен на сервере PostgreSQL")
        print("   • Недостаточно прав для создания расширений")
        print("   • Нужно установить: apt-get install postgresql-15-pgvector")
        return False
    finally:
        db.close()

def create_vector_indexes():
    """Создаем векторные индексы для ускорения поиска"""
    print("\n📇 Создание векторных индексов...")
    
    db = SessionLocal()
    try:
        # Создаем IVFFLAT индекс для косинусного расстояния
        print("🔨 Создаем IVFFLAT индекс...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_cosine 
            ON document_chunks 
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        
        # Создаем HNSW индекс (более быстрый, но больше памяти)
        print("🔨 Создаем HNSW индекс...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw 
            ON document_chunks 
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        
        db.commit()
        print("✅ Векторные индексы созданы")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания индексов: {e}")
        print("💡 Индексы можно создать только после установки pgvector")
        return False
    finally:
        db.close()

def convert_to_vector_type():
    """Конвертируем ARRAY(Float) в тип VECTOR"""
    print("\n🔄 Конвертация в тип VECTOR...")
    
    db = SessionLocal()
    try:
        # Добавляем новую колонку с типом VECTOR
        print("📝 Добавляем колонку vector_embedding...")
        db.execute(text("""
            ALTER TABLE document_chunks 
            ADD COLUMN IF NOT EXISTS vector_embedding vector(312)
        """))
        
        # Копируем данные из ARRAY в VECTOR
        print("📋 Копируем данные...")
        db.execute(text("""
            UPDATE document_chunks 
            SET vector_embedding = embedding::vector
            WHERE embedding IS NOT NULL AND vector_embedding IS NULL
        """))
        
        db.commit()
        print("✅ Конвертация завершена")
        
        # Проверяем результат
        result = db.execute(text("""
            SELECT COUNT(*) FROM document_chunks 
            WHERE vector_embedding IS NOT NULL
        """)).fetchall()
        
        print(f"📊 Конвертировано записей: {result[0][0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка конвертации: {e}")
        return False
    finally:
        db.close()

def test_vector_performance():
    """Тестируем производительность векторного поиска"""
    print("\n⚡ Тестирование производительности...")
    
    db = SessionLocal()
    try:
        import time
        
        # Тестовый вектор
        test_vector = "[" + ",".join(["0.1"] * 312) + "]"
        
        # Тест с ARRAY (текущий метод)
        start_time = time.time()
        result1 = db.execute(text(f"""
            SELECT id, embedding <=> '{test_vector}'::vector as distance
            FROM document_chunks 
            WHERE embedding IS NOT NULL
            ORDER BY distance
            LIMIT 10
        """)).fetchall()
        array_time = time.time() - start_time
        
        # Тест с VECTOR (оптимизированный)
        start_time = time.time()
        result2 = db.execute(text(f"""
            SELECT id, vector_embedding <=> '{test_vector}'::vector as distance
            FROM document_chunks 
            WHERE vector_embedding IS NOT NULL
            ORDER BY distance
            LIMIT 10
        """)).fetchall()
        vector_time = time.time() - start_time
        
        print(f"📊 Результаты тестирования:")
        print(f"   ARRAY метод: {array_time:.3f} сек")
        print(f"   VECTOR метод: {vector_time:.3f} сек")
        print(f"   Ускорение: {array_time/vector_time:.1f}x")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return False
    finally:
        db.close()

def main():
    """Основная функция"""
    print("🚀 Установка и настройка pgvector\n")
    
    # Устанавливаем pgvector
    pgvector_ok = install_pgvector()
    
    if pgvector_ok:
        # Создаем индексы
        indexes_ok = create_vector_indexes()
        
        # Конвертируем данные
        convert_ok = convert_to_vector_type()
        
        if convert_ok:
            # Тестируем производительность
            test_vector_performance()
    
    print("\n" + "="*60)
    print("📊 ИТОГИ УСТАНОВКИ:")
    print("="*60)
    
    if pgvector_ok:
        print("🎉 pgvector успешно установлен!")
        print("✅ Теперь доступны:")
        print("   • Нативные векторные операторы (<->, <=>, <#>)")
        print("   • Векторные индексы (IVFFLAT, HNSW)")
        print("   • Оптимизированный поиск")
        print("   • Лучшая производительность")
        
        print("\n💡 Следующие шаги:")
        print("   1. Обновите модель DocumentChunk для использования Vector типа")
        print("   2. Измените поисковые запросы на нативные операторы")
        print("   3. Протестируйте улучшенную производительность")
    else:
        print("⚠️ pgvector не установлен")
        print("💡 Обратитесь к администратору БД для установки")

if __name__ == "__main__":
    main() 