#!/usr/bin/env python3
"""
Скрипт для проверки структуры базы данных
"""

import os
import sys
from pathlib import Path
import psycopg2

# Добавляем путь к проекту
current_dir = Path(__file__).parent
services_dir = current_dir.parent
sys.path.insert(0, str(services_dir))

from dotenv import load_dotenv
load_dotenv('.env.local')

def check_documents_table():
    """Проверяем структуру таблицы documents"""
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cur = conn.cursor()
        
        print("📋 СТРУКТУРА ТАБЛИЦЫ DOCUMENTS:")
        print("=" * 50)
        
        # Получаем структуру таблицы
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'documents' 
            ORDER BY ordinal_position;
        """)
        
        columns = cur.fetchall()
        for col in columns:
            nullable = "NULL" if col[2] == "YES" else "NOT NULL"
            default = f" DEFAULT {col[3]}" if col[3] else ""
            print(f"  {col[0]}: {col[1]} {nullable}{default}")
        
        print("\n📊 ДАННЫЕ В ТАБЛИЦЕ DOCUMENTS:")
        print("=" * 50)
        
        # Получаем данные из таблицы
        cur.execute("SELECT id, filename, uploaded_by, processing_status FROM documents ORDER BY id;")
        docs = cur.fetchall()
        
        for doc in docs:
            print(f"  ID: {doc[0]}, Файл: {doc[1]}, Загружен: {doc[2]}, Статус: {doc[3]}")
        
        print("\n👥 ТАБЛИЦА ADMINS:")
        print("=" * 50)
        
        # Проверяем таблицу администраторов
        cur.execute("SELECT id, username, full_name FROM admins ORDER BY id;")
        admins = cur.fetchall()
        
        for admin in admins:
            print(f"  ID: {admin[0]}, Username: {admin[1]}, ФИО: {admin[2]}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    check_documents_table() 