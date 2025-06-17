"""
Модуль для работы с базой данных в Telegram боте
"""

import logging
import os
import sys
from pathlib import Path
from typing import Generator
import asyncio

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# Добавляем путь к shared модулям
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "shared"))

try:
    # Попытка импорта из shared (для Docker)
    from shared.models.database import Base
    from shared.models.user import User
    from shared.models.admin import Admin
    from shared.models.document import Document, DocumentChunk
    from shared.models.query_log import QueryLog
    from shared.models.menu import MenuSection, MenuItem
except ImportError:
    # Fallback для локальной разработки
    sys.path.insert(0, str(project_root / "services" / "shared"))
    from models.database import Base
    from models.user import User
    from models.admin import Admin
    from models.document import Document, DocumentChunk
    from models.query_log import QueryLog
    from models.menu import MenuSection, MenuItem

logger = logging.getLogger(__name__)

# Глобальные переменные для подключения к БД
engine = None
SessionLocal = None

def init_database():
    """Инициализация подключения к базе данных"""
    global engine, SessionLocal
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL не найден в переменных окружения")
    
    try:
        # Создаем движок базы данных
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False  # Установите True для отладки SQL запросов
        )
        
        # Создаем фабрику сессий
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
        
        logger.info("✅ Подключение к базе данных установлено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе данных: {e}")
        raise

async def init_db():
    """Асинхронная инициализация базы данных"""
    try:
        # Инициализируем подключение
        init_database()
        
        # Создаем таблицы, если их нет
        Base.metadata.create_all(bind=engine)
        
        logger.info("✅ База данных инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        raise

def get_db_session() -> Generator[Session, None, None]:
    """
    Получение сессии базы данных
    
    Yields:
        Session: Сессия SQLAlchemy
    """
    if SessionLocal is None:
        init_database()
    
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Ошибка в сессии БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
    """
    Получение или создание пользователя
    
    Args:
        telegram_id: ID пользователя в Telegram
        username: Username пользователя
        first_name: Имя пользователя
        last_name: Фамилия пользователя
        
    Returns:
        User: Объект пользователя
    """
    db = next(get_db_session())
    
    try:
        # Ищем существующего пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if user:
            # Обновляем информацию, если она изменилась
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                db.commit()
                logger.info(f"Обновлена информация пользователя {telegram_id}")
            
            return user
        
        # Создаем нового пользователя
        new_user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_active=True
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"Создан новый пользователь: {telegram_id} ({username})")
        return new_user
        
    except Exception as e:
        logger.error(f"Ошибка при работе с пользователем {telegram_id}: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def log_user_query(user_id: int, query: str, response_text: str, 
                   response_time: float = None, similarity_score: float = None, 
                   documents_used: str = None) -> bool:
    """
    Логирование запроса пользователя
    
    Args:
        user_id: ID пользователя
        query: Текст запроса
        response_text: Текст ответа
        response_time: Время ответа в секундах
        similarity_score: Оценка релевантности
        documents_used: JSON со списком использованных документов
        
    Returns:
        bool: Успешность операции
    """
    db = next(get_db_session())
    
    try:
        query_log = QueryLog(
            user_id=user_id,
            query=query,
            response=response_text,
            response_time=response_time,
            similarity_score=similarity_score,
            documents_used=documents_used
        )
        
        db.add(query_log)
        db.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка логирования запроса: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def get_user_stats(telegram_id: int) -> dict:
    """
    Получение статистики пользователя
    
    Args:
        telegram_id: ID пользователя в Telegram
        
    Returns:
        dict: Статистика пользователя
    """
    db = next(get_db_session())
    
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return {'error': 'Пользователь не найден'}
        
        # Подсчитываем количество запросов
        query_count = db.query(QueryLog).filter(QueryLog.user_id == user.id).count()
        
        # Получаем последний запрос
        last_query = db.query(QueryLog).filter(
            QueryLog.user_id == user.id
        ).order_by(QueryLog.created_at.desc()).first()
        
        return {
            'user_id': user.id,
            'telegram_id': user.telegram_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'created_at': user.created_at,
            'query_count': query_count,
            'last_query_at': last_query.created_at if last_query else None
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики пользователя {telegram_id}: {e}")
        return {'error': str(e)}
    finally:
        db.close()

def check_database_health() -> bool:
    """
    Проверка работоспособности базы данных
    
    Returns:
        bool: True если БД работает
    """
    try:
        db = next(get_db_session())
        # Простой запрос для проверки подключения
        db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки БД: {e}")
        return False
    finally:
        if 'db' in locals():
            db.close()

def get_documents_count() -> int:
    """
    Получение количества документов в базе
    
    Returns:
        int: Количество документов
    """
    try:
        db = next(get_db_session())
        count = db.query(Document).filter(Document.processing_status == 'completed').count()
        return count
    except Exception as e:
        logger.error(f"Ошибка подсчета документов: {e}")
        return 0
    finally:
        if 'db' in locals():
            db.close()

def get_menu_sections():
    """Получить все разделы меню FAQ"""
    try:
        db = next(get_db_session())
        sections = db.query(MenuSection).order_by(MenuSection.order_index).all()
        return [{"id": s.id, "title": s.title} for s in sections]
    except Exception as e:
        logger.error(f"Ошибка получения разделов меню: {e}")
        return []
    finally:
        db.close()

def get_menu_items(section_id: int):
    """Получить все элементы меню для раздела"""
    try:
        db = next(get_db_session())
        items = db.query(MenuItem).filter(
            MenuItem.section_id == section_id
        ).order_by(MenuItem.order_index).all()
        return [{"id": i.id, "title": i.title, "content": i.content} for i in items]
    except Exception as e:
        logger.error(f"Ошибка получения элементов меню: {e}")
        return []
    finally:
        db.close()

def get_menu_item_content(item_id: int):
    """Получить содержимое элемента меню с информацией об источниках"""
    try:
        db = next(get_db_session())
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if item:
            import json
            
            # Парсим JSON поля источников
            source_document_ids = []
            source_document_names = []
            source_chunk_ids = []
            
            try:
                if item.source_document_ids:
                    source_document_ids = json.loads(item.source_document_ids)
                if item.source_document_names:
                    source_document_names = json.loads(item.source_document_names)
                if item.source_chunk_ids:
                    source_chunk_ids = json.loads(item.source_chunk_ids)
            except json.JSONDecodeError:
                logger.warning(f"Ошибка парсинга JSON источников для элемента {item_id}")
            
            return {
                "title": item.title, 
                "content": item.content,
                "source_document_ids": source_document_ids,
                "source_document_names": source_document_names,
                "source_chunk_ids": source_chunk_ids
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка получения содержимого элемента: {e}")
        return None
    finally:
        db.close()

def get_documents_by_ids(document_ids: list):
    """Получить документы по списку ID"""
    try:
        db = next(get_db_session())
        
        if not document_ids:
            return []
        
        documents = db.query(Document).filter(Document.id.in_(document_ids)).all()
        result = []
        
        for doc in documents:
            result.append({
                'title': doc.title or doc.original_filename,
                'original_filename': doc.original_filename,
                'created_at': doc.created_at
            })
        
        return result
    except Exception as e:
        logger.error(f"Ошибка получения документов по ID: {e}")
        return []
    finally:
        db.close()

def get_completed_documents(limit: int = None, offset: int = None):
    """Получить список завершенных документов с пагинацией"""
    try:
        db = next(get_db_session())
        query = db.query(Document).filter(Document.processing_status == 'completed').order_by(Document.created_at.desc())
        
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
            
        documents = query.all()
        
        result = []
        for doc in documents:
            result.append({
                'id': doc.id,
                'title': doc.title or doc.original_filename,
                'original_filename': doc.original_filename,
                'file_path': doc.file_path,
                'file_type': doc.file_type,
                'file_size': doc.file_size,
                'created_at': doc.created_at,
                'status': doc.processing_status
            })
        
        return result
    except Exception as e:
        logger.error(f"Ошибка получения завершенных документов: {e}")
        return []
    finally:
        db.close()

def get_completed_documents_count():
    """Получить общее количество завершенных документов"""
    try:
        db = next(get_db_session())
        count = db.query(Document).filter(Document.processing_status == 'completed').count()
        return count
    except Exception as e:
        logger.error(f"Ошибка получения количества завершенных документов: {e}")
        return 0
    finally:
        db.close()

def get_document_by_id(doc_id: int):
    """Получить документ по ID"""
    try:
        db = next(get_db_session())
        document = db.query(Document).filter(Document.id == doc_id).first()
        
        if not document:
            return None
            
        return {
            'id': document.id,
            'title': document.title or document.original_filename,
            'original_filename': document.original_filename,
            'file_path': document.file_path,
            'file_type': document.file_type,
            'file_size': document.file_size,
            'created_at': document.created_at,
            'status': document.processing_status
        }
    except Exception as e:
        logger.error(f"Ошибка получения документа по ID {doc_id}: {e}")
        return None
    finally:
        db.close() 