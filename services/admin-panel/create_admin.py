#!/usr/bin/env python3
"""
Скрипт для создания администратора admin/poliom_$487%0_admin
Используется для первоначальной настройки системы
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к shared модулям
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(current_dir))

# Загружаем переменные окружения
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Загружен .env файл: {env_path}")
else:
    print(f"⚠️ .env файл не найден: {env_path}")

from shared.models.database import get_session, init_database
from shared.models.admin import Admin
from shared.utils.auth import get_password_hash, verify_password

def create_default_admin():
    """Создаем администратора admin/poliom_$487%0_admin"""
    print("🔧 Создаем администратора admin/poliom_$487%0_admin...")
    
    try:
        # Инициализируем базу данных
        init_database()
        
        # Получаем сессию
        db = get_session()
        
        try:
            # Проверяем, есть ли уже администратор admin
            existing_admin = db.query(Admin).filter(Admin.username == "admin").first()
            
            if existing_admin:
                print("👤 Администратор 'admin' уже существует. Обновляем пароль...")
                # Обновляем пароль
                existing_admin.hashed_password = get_password_hash("poliom_$487%0_admin")
                existing_admin.is_active = True
                existing_admin.email = "admin@poliom.com"
                existing_admin.full_name = "Системный администратор"
                db.commit()
                print("✅ Пароль администратора обновлен")
            else:
                print("👤 Создаем нового администратора...")
                # Создаем нового администратора
                admin_user = Admin(
                    username="admin",
                    email="admin@poliom.com", 
                    hashed_password=get_password_hash("poliom_$487%0_admin"),
                    full_name="Системный администратор",
                    is_active=True
                )
                
                db.add(admin_user)
                db.commit()
                print("✅ Администратор создан")
            
            # Проверяем корректность пароля
            admin_user = db.query(Admin).filter(Admin.username == "admin").first()
            password_check = verify_password("poliom_$487%0_admin", admin_user.hashed_password)
            print(f"🔐 Проверка пароля 'poliom_$487%0_admin': {password_check}")
            
            if password_check:
                print("🎉 Администратор успешно создан!")
                print("📝 Данные для входа:")
                print("   Логин: admin")
                print("   Пароль: poliom_$487%0_admin")
                print("   URL: http://localhost:8001")
            else:
                print("❌ Ошибка: пароль не работает")
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    
    return True

if __name__ == "__main__":
    create_default_admin() 