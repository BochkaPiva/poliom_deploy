#!/usr/bin/env python3
"""
Скрипт для проверки и создания администратора
"""

import os
import sys
from pathlib import Path

# Загружаем переменные окружения из .env
from dotenv import load_dotenv
load_dotenv('.env')

# Добавляем пути к модулям
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "shared"))

# Импортируем shared модули
try:
    # Пробуем импорт для Docker
    from shared.utils.auth import get_password_hash, verify_password
    from shared.models.database import SessionLocal, engine, Base
    from shared.models import Admin
except ImportError:
    # Если не получилось, пробуем локальный импорт
    from utils.auth import get_password_hash, verify_password
    from models.database import SessionLocal, engine, Base
    from models import Admin

# Выводим информацию о подключении
print(f"🔗 Подключение к БД:")
print(f"  Host: {os.getenv('POSTGRES_HOST', 'localhost')}")
print(f"  Port: {os.getenv('POSTGRES_PORT', '5432')}")
print(f"  Database: {os.getenv('POSTGRES_DB', 'rag_chatbot')}")
print(f"  User: {os.getenv('POSTGRES_USER', 'postgres')}")
print(f"  Password: {'*' * len(os.getenv('POSTGRES_PASSWORD', ''))}")

def check_and_create_admin():
    """Проверяем и создаем администратора"""
    print("\n🔍 Проверяем базу данных...")
    
    # Создаем таблицы
    Base.metadata.create_all(bind=engine)
    print("✅ Таблицы созданы")
    
    db = SessionLocal()
    try:
        # Проверяем существующих администраторов
        admins = db.query(Admin).all()
        print(f"📊 Найдено администраторов: {len(admins)}")
        
        for admin in admins:
            print(f"  - ID: {admin.id}, Username: {admin.username}, Email: {admin.email}, Active: {admin.is_active}")
        
        # Создаем администратора по умолчанию если его нет
        admin_count = db.query(Admin).count()
        if admin_count == 0:
            print("👤 Администраторов не найдено. Создаем по умолчанию...")
            default_admin = Admin(
                username="admin",
                email="admin@poliom.com",
                hashed_password=get_password_hash("poliom_$487%0_admin"),
                full_name="Системный администратор",
                is_active=True
            )
            db.add(default_admin)
            db.commit()
            print("✅ Создан администратор по умолчанию")
        
        # Проверяем администратора 'admin'
        admin_user = db.query(Admin).filter(Admin.username == "admin").first()
        if admin_user:
            print(f"✅ Найден администратор: {admin_user.username}")
            print(f"   Email: {admin_user.email}")
            print(f"   Активен: {admin_user.is_active}")
            print(f"   Полное имя: {admin_user.full_name}")
            
            # Проверяем пароль
            password_check = verify_password("poliom_$487%0_admin", admin_user.hashed_password)
            print(f"  - Пароль 'poliom_$487%0_admin' корректен: {password_check}")
            
            if not password_check:
                print("🔧 Обновляем пароль...")
                new_hash = get_password_hash("poliom_$487%0_admin")
                admin_user.hashed_password = new_hash
                db.commit()
                print("✅ Пароль обновлен")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_and_create_admin() 