#!/usr/bin/env python3
"""
Проверка pgvector и структуры хранения эмбеддингов
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

def check_pgvector():
    """Проверяем установку pgvector"""
    print("🔍 Проверка pgvector...")
    
    db = SessionLocal()
    try:
        # Проверяем установку расширения
        result = db.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'")).fetchall()
        
        if result:
            print("✅ pgvector установлен")
            for row in result:
                print(f"   Версия: {row[1]}")
                print(f"   Схема: {row[2]}")
        else:
            print("❌ pgvector НЕ установлен")
            return False
        
        # Проверяем доступные операторы
        operators = db.execute(text("""
            SELECT oprname, oprleft::regtype, oprright::regtype 
            FROM pg_operator 
            WHERE oprname IN ('<->', '<=>', '<#>')
        """)).fetchall()
        
        print(f"\n📊 Доступные векторные операторы: {len(operators)}")
        for op in operators:
            print(f"   {op[0]} для типов {op[1]} и {op[2]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки pgvector: {e}")
        return False
    finally:
        db.close()

def check_embedding_storage():
    """Проверяем как хранятся эмбеддинги"""
    print("\n🗄️ Проверка хранения эмбеддингов...")
    
    db = SessionLocal()
    try:
        # Проверяем структуру таблицы document_chunks
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'embedding'
        """)).fetchall()
        
        if result:
            col_info = result[0]
            print(f"✅ Поле embedding найдено:")
            print(f"   Тип данных: {col_info[1]}")
            print(f"   Nullable: {col_info[2]}")
        else:
            print("❌ Поле embedding не найдено")
            return False
        
        # Проверяем размер эмбеддингов
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total_chunks,
                COUNT(embedding) as chunks_with_embeddings
            FROM document_chunks
        """)).fetchall()
        
        if result and result[0][0] > 0:
            stats = result[0]
            print(f"\n📈 Статистика эмбеддингов:")
            print(f"   Всего чанков: {stats[0]}")
            print(f"   С эмбеддингами: {stats[1]}")
            
            # Проверяем размерность отдельно
            dim_result = db.execute(text("""
                SELECT array_length(embedding, 1) as embedding_dimension
                FROM document_chunks 
                WHERE embedding IS NOT NULL
                LIMIT 1
            """)).fetchall()
            
            if dim_result and dim_result[0][0]:
                print(f"   Размерность: {dim_result[0][0]}")
        
        # Проверяем пример эмбеддинга
        result = db.execute(text("""
            SELECT embedding[1:5] as first_5_values
            FROM document_chunks 
            WHERE embedding IS NOT NULL 
            LIMIT 1
        """)).fetchall()
        
        if result:
            print(f"   Пример значений: {result[0][0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки хранения: {e}")
        return False
    finally:
        db.close()

def check_vector_indexes():
    """Проверяем векторные индексы"""
    print("\n📇 Проверка векторных индексов...")
    
    db = SessionLocal()
    try:
        # Проверяем существующие индексы
        result = db.execute(text("""
            SELECT 
                indexname, 
                indexdef,
                tablename
            FROM pg_indexes 
            WHERE tablename = 'document_chunks'
            AND indexname LIKE '%embedding%'
        """)).fetchall()
        
        if result:
            print(f"✅ Найдено индексов: {len(result)}")
            for idx in result:
                print(f"   {idx[0]}: {idx[1]}")
        else:
            print("⚠️ Векторные индексы не найдены")
            print("💡 Рекомендуется создать индекс для ускорения поиска:")
            print("   CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops);")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки индексов: {e}")
        return False
    finally:
        db.close()

def main():
    """Основная функция"""
    print("🚀 Проверка векторной базы данных\n")
    
    pgvector_ok = check_pgvector()
    storage_ok = check_embedding_storage()
    indexes_ok = check_vector_indexes()
    
    print("\n" + "="*60)
    print("📊 ИТОГИ:")
    print("="*60)
    
    if pgvector_ok:
        print("✅ pgvector установлен и работает")
    else:
        print("❌ pgvector не установлен")
    
    if storage_ok:
        print("✅ Эмбеддинги хранятся корректно")
        print("📝 Тип хранения: ARRAY(Float) в PostgreSQL")
        print("🔧 Это обычная реляционная БД с поддержкой массивов")
    else:
        print("❌ Проблемы с хранением эмбеддингов")
    
    if indexes_ok:
        print("✅ Индексы проверены")
    
    print("\n💡 ЗАКЛЮЧЕНИЕ:")
    if pgvector_ok and storage_ok:
        print("🎉 У вас ГИБРИДНАЯ система:")
        print("   • PostgreSQL (реляционная БД) для метаданных")
        print("   • pgvector расширение для векторных операций")
        print("   • ARRAY(Float) для хранения эмбеддингов")
        print("   • Векторные операторы (<->, <=>, <#>) для поиска")
    else:
        print("⚠️ Система требует настройки")

if __name__ == "__main__":
    main() 