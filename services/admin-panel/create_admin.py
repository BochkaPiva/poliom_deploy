#!/usr/bin/env python3
"""
Скрипт для создания администратора admin/admin123
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

def create_admin():
    """Создаем администратора admin/admin123"""
    print("🔧 Создаем администратора admin/admin123...")
    
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже admin
        existing_admin = db.query(Admin).filter(Admin.username == "admin").first()
        
        if existing_admin:
            print("⚠️  Администратор 'admin' уже существует!")
            print(f"   ID: {existing_admin.id}")
            print(f"   Email: {existing_admin.email}")
            print(f"   Active: {existing_admin.is_active}")
            
            # Обновляем пароль
            print("🔧 Обновляем пароль...")
            existing_admin.hashed_password = get_password_hash("admin123")
            db.commit()
            print("✅ Пароль обновлен!")
            
        else:
            # Создаем нового администратора
            new_admin = Admin(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin123"),
                full_name="Администратор по умолчанию",
                is_active=True
            )
            db.add(new_admin)
            db.commit()
            db.refresh(new_admin)
            print(f"✅ Создан администратор: {new_admin.username} (ID: {new_admin.id})")
        
        # Проверяем пароль
        admin_user = db.query(Admin).filter(Admin.username == "admin").first()
        if admin_user:
            password_check = verify_password("admin123", admin_user.hashed_password)
            print(f"🔐 Проверка пароля 'admin123': {password_check}")
            
            if password_check:
                print("✅ Администратор готов к использованию!")
                print("   Логин: admin")
                print("   Пароль: admin123")
            else:
                print("❌ Ошибка проверки пароля!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin() 