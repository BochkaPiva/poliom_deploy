#!/usr/bin/env python3
"""
Скрипт для перезапуска документов, застрявших в статусе 'processing'
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Добавляем путь к services
current_dir = Path(__file__).parent
services_dir = current_dir.parent
sys.path.insert(0, str(services_dir))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv('.env.local')

from sqlalchemy.orm import sessionmaker
from shared.models.database import engine
from shared.models import Document
from tasks import process_document

# Создаем сессию базы данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def restart_stuck_documents():
    """Перезапускает документы застрявшие в статусе processing"""
    db = SessionLocal()
    
    try:
        # Находим все документы в статусе processing
        stuck_documents = db.query(Document).filter(
            Document.processing_status == "processing"
        ).all()
        
        if not stuck_documents:
            logger.info("Нет документов в статусе 'processing'")
            return
        
        logger.info(f"Найдено {len(stuck_documents)} документов в статусе 'processing'")
        
        for document in stuck_documents:
            logger.info(f"Перезапускаем документ {document.id}: {document.original_filename}")
            
            try:
                # Сбрасываем статус на pending
                document.processing_status = "pending"
                document.updated_at = datetime.utcnow()
                db.commit()
                
                # Запускаем задачу обработки
                task = process_document.delay(document.id)
                logger.info(f"Запущена задача {task.id} для документа {document.id}")
                
            except Exception as e:
                logger.error(f"Ошибка перезапуска документа {document.id}: {e}")
                db.rollback()
        
        logger.info("Перезапуск завершен")
        
    except Exception as e:
        logger.error(f"Ошибка при перезапуске документов: {e}")
        
    finally:
        db.close()


if __name__ == "__main__":
    restart_stuck_documents() 